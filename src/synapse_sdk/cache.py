"""SYNAPSE Adapter SDK — §8 Caching Architecture (C1–C5).

Five cache layers, each with independent storage, TTL, eviction, and
invalidation logic.  Every layer degrades gracefully on failure — a cache
miss or store failure MUST fall through to the live computation or data
source and MUST NOT cause a pipeline request to fail.
"""

from __future__ import annotations

import atexit
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Supporting types — lightweight SDK-side definitions for routing / heartbeat /
# calibration; the registry owns the authoritative schema, these are the
# SDK-level mirror types sufficient for cache key construction and storage.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RouteCandidate:
    model_id: str
    adapter_version: str
    score: float
    estimated_latency_ms: int | None = None
    estimated_cost_usd: float | None = None


@dataclass
class RouteRequest:
    task_type: str
    domain: str
    latency_budget_ms: int
    compliance_tags: list[str] | None = None
    cost_ceiling: float | None = None
    quality_floor: float | None = None
    exclude_models: list[str] | None = None
    limit: int = 5


@dataclass
class RouteResponse:
    candidates: list[RouteCandidate]
    filtered_out: list[RouteCandidate] = field(default_factory=list)
    cached_at: float = field(default_factory=time.time)
    ttl_seconds: int = 30
    hit_count: int = 0


@dataclass
class HeartbeatResponse:
    model_id: str
    status: str  # "available" | "degraded" | "unavailable"
    capacity_pct: float = 1.0
    latency_p50_ms: int | None = None
    latency_p99_ms: int | None = None
    error_rate: float = 0.0
    version: str | None = None


@dataclass
class CalibrationSignal:
    model_id: str
    adapter_version: str
    task_type: str
    domain: str
    latency_ms: int
    confidence: float
    timestamp_unix: float = field(default_factory=time.time)
    cost_usd: float | None = None
    token_count: int | None = None
    session_id: str | None = None
    pipeline_hop: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Custom errors
# ─────────────────────────────────────────────────────────────────────────────

class AdapterLoadError(RuntimeError):
    """Raised when C1 cannot resolve or instantiate an adapter for a model."""


# ─────────────────────────────────────────────────────────────────────────────
# C1 — AdapterInstanceCache
# ─────────────────────────────────────────────────────────────────────────────

class AdapterInstanceCache:
    """C1: Thread-safe in-process LRU cache of AdapterBase instances.

    Key format: ``'{model_id}:{adapter_version}'``
    Max entries: SYNAPSE_ADAPTER_CACHE_MAX (default 256).
    Eviction: LRU.  TTL: none (permanent until explicit invalidation).

    Double-checked locking pattern: the cache is checked once under lock for
    the fast hit path; on a miss the slow import runs *outside* the lock, then
    the lock is re-acquired to write — preventing a thundering-herd where every
    concurrent miss would hold the lock during import.
    """

    _cache: OrderedDict[str, Any] = OrderedDict()
    _lock = threading.Lock()
    _max: int = int(os.getenv("SYNAPSE_ADAPTER_CACHE_MAX", "256"))
    _eager_load: bool = os.getenv("SYNAPSE_ADAPTER_EAGER_LOAD", "false").lower() == "true"

    # Prometheus-compatible counters (replace with real counters in production)
    _hits_total: int = 0
    _misses_total: int = 0

    @classmethod
    def get(cls, model_id: str, version: str) -> Any:
        """Return the cached AdapterBase instance, loading it if necessary.

        Raises AdapterLoadError (not a cache miss) when the adapter package
        cannot be resolved — this is a configuration error, not a transient
        failure, and the pipeline should surface it immediately.
        """
        key = f"{model_id}:{version}"

        # Fast path — check under lock, return immediately on hit
        with cls._lock:
            if key in cls._cache:
                cls._cache.move_to_end(key)
                cls._hits_total += 1
                return cls._cache[key]

        # Slow path — load outside lock so import machinery doesn't stall readers
        cls._misses_total += 1
        instance = cls._load(model_id, version)

        # Second check — another thread may have raced us to load the same key
        with cls._lock:
            if key in cls._cache:
                cls._cache.move_to_end(key)
                return cls._cache[key]
            if len(cls._cache) >= cls._max:
                evicted, _ = cls._cache.popitem(last=False)
                log.debug("adapter_cache_evict: key=%s", evicted)
            cls._cache[key] = instance

        return instance

    @classmethod
    def invalidate(cls, model_id: str, version: str) -> None:
        """Remove a specific adapter instance from the cache."""
        key = f"{model_id}:{version}"
        with cls._lock:
            cls._cache.pop(key, None)
        log.debug("adapter_cache_invalidate: key=%s", key)

    @classmethod
    def _load(cls, model_id: str, version: str) -> Any:
        """Resolve the adapter package, import it, and return an instance.

        The default implementation raises AdapterLoadError.  Integrators
        should either subclass and override this method, or register adapters
        via ``AdapterInstanceCache.register()``.
        """
        loader = cls._registry.get(f"{model_id}:{version}")
        if loader is not None:
            return loader()
        raise AdapterLoadError(
            f"No adapter registered for model_id={model_id!r} version={version!r}. "
            "Call AdapterInstanceCache.register() before first use, or subclass "
            "AdapterInstanceCache and override _load()."
        )

    # Pluggable loader registry: key -> zero-arg callable returning AdapterBase
    _registry: dict[str, Any] = {}

    @classmethod
    def register(cls, model_id: str, version: str, factory) -> None:
        """Register a zero-arg callable that constructs an adapter instance."""
        cls._registry[f"{model_id}:{version}"] = factory

    @classmethod
    def metrics(cls) -> dict[str, int]:
        return {
            "synapse_adapter_cache_hits_total": cls._hits_total,
            "synapse_adapter_cache_misses_total": cls._misses_total,
            "size": len(cls._cache),
        }


# ─────────────────────────────────────────────────────────────────────────────
# C2 — RouteCacheClient
# ─────────────────────────────────────────────────────────────────────────────

def _route_cache_key(request: RouteRequest) -> str:
    """Build a 32-hex-char SHA-256 key from normalized RouteRequest fields.

    Array fields are sorted before hashing so that field-order differences
    (e.g. ``['pii', 'gdpr']`` vs ``['gdpr', 'pii']``) produce the same key.
    """
    components = [
        request.task_type,
        request.domain,
        str(request.latency_budget_ms),
        ",".join(sorted(request.compliance_tags or [])),
        str(request.cost_ceiling or ""),
        str(request.quality_floor or ""),
        ",".join(sorted(request.exclude_models or [])),
        str(request.limit if request.limit is not None else 5),
    ]
    return hashlib.sha256(":".join(components).encode()).hexdigest()[:32]


class _L1Entry:
    __slots__ = ("response", "cached_at", "ttl", "hit_count")

    def __init__(self, response: RouteResponse, ttl: int) -> None:
        self.response = response
        self.cached_at = time.monotonic()
        self.ttl = ttl
        self.hit_count: int = 0

    def is_expired(self) -> bool:
        return (time.monotonic() - self.cached_at) >= self.ttl

    def remaining_ttl(self) -> float:
        return max(0.0, self.ttl - (time.monotonic() - self.cached_at))


class RouteCacheClient:
    """C2: Two-tier routing decision cache.

    L1: in-process LRU (always present, ~0.01 ms lookup).
    L2: Redis (optional, ~0.5–2 ms lookup, shared across SDK instances).

    TTL range: 5–300 s, default 30 s (SYNAPSE_ROUTE_CACHE_TTL_SECONDS).
    When L2 is present, L1 TTL = min(remaining_redis_ttl, 10s) so L1 never
    outlives L2.
    """

    # Class-level Prometheus-compatible counters
    _hits_total: int = 0
    _misses_total: int = 0
    _invalidations_total: int = 0

    def __init__(self) -> None:
        raw_ttl = int(os.getenv("SYNAPSE_ROUTE_CACHE_TTL_SECONDS", "30"))
        self._ttl: int = max(5, min(300, raw_ttl))
        self._max: int = int(os.getenv("SYNAPSE_ROUTE_CACHE_MAX_ENTRIES", "1000"))
        redis_url = os.getenv("SYNAPSE_ROUTE_CACHE_REDIS_URL") or None

        self._l1: OrderedDict[str, _L1Entry] = OrderedDict()
        self._lock = threading.Lock()

        self._redis = None
        if redis_url:
            self._redis = self._connect_redis(redis_url)

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, request: RouteRequest) -> RouteResponse | None:
        """Return a cached RouteResponse, or None on miss."""
        key = _route_cache_key(request)

        # L1 check
        with self._lock:
            entry = self._l1.get(key)
            if entry is not None:
                if not entry.is_expired():
                    self._l1.move_to_end(key)
                    entry.hit_count += 1
                    RouteCacheClient._hits_total += 1
                    return entry.response
                del self._l1[key]

        # L2 (Redis) check
        if self._redis is not None:
            result = self._redis_get(key)
            if result is not None:
                remaining = self._redis_ttl(key)
                l1_ttl = max(1, int(min(remaining, 10)))
                self._l1_set(key, result, l1_ttl)
                RouteCacheClient._hits_total += 1
                return result

        RouteCacheClient._misses_total += 1
        return None

    def set(self, request: RouteRequest, response: RouteResponse) -> None:
        """Cache a routing decision.  Silently drops on any storage failure."""
        key = _route_cache_key(request)
        try:
            self._l1_set(key, response, self._ttl)
            if self._redis is not None:
                self._redis_set(key, response, self._ttl)
        except Exception as exc:
            log.warning("route_cache_set_failed: %s", exc)

    def invalidate(self, key: str) -> None:
        """Evict a single cache entry by its pre-computed hash key."""
        with self._lock:
            self._l1.pop(key, None)
        if self._redis is not None:
            try:
                self._redis.delete(f"synapse:route:{key}")
            except Exception as exc:
                log.warning("route_cache_redis_invalidate_failed: %s", exc)
        RouteCacheClient._invalidations_total += 1

    def invalidate_model(self, model_id: str) -> None:
        """Remove all L1 entries that contain model_id in candidates or filtered_out.

        Called on model manifest update or heartbeat=unavailable events (§8.6).
        Redis entries expire naturally via TTL — full Redis scan is not performed.
        """
        evict: list[str] = []
        with self._lock:
            for key, entry in self._l1.items():
                resp = entry.response
                ids = {c.model_id for c in resp.candidates} | {c.model_id for c in resp.filtered_out}
                if model_id in ids:
                    evict.append(key)
            for k in evict:
                del self._l1[k]
        RouteCacheClient._invalidations_total += len(evict)
        if evict:
            log.debug("route_cache_invalidate_model: model=%s evicted=%d", model_id, len(evict))

    # ── L1 internals ──────────────────────────────────────────────────────────

    def _l1_set(self, key: str, response: RouteResponse, ttl: int) -> None:
        with self._lock:
            if key in self._l1:
                self._l1.move_to_end(key)
            elif len(self._l1) >= self._max:
                self._l1.popitem(last=False)
            self._l1[key] = _L1Entry(response, ttl)

    # ── Redis internals (graceful fallback on any error) ──────────────────────

    def _connect_redis(self, url: str):
        try:
            import redis as _redis  # optional dependency
            client = _redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            log.info("route_cache_redis_connected: url=%s", url)
            return client
        except Exception as exc:
            log.warning("route_cache_redis_unavailable: %s — using in-process cache only", exc)
            return None

    def _redis_get(self, key: str) -> RouteResponse | None:
        try:
            import pickle
            raw = self._redis.get(f"synapse:route:{key}")
            if raw:
                return pickle.loads(raw)  # noqa: S301 — trusted internal cache bytes
        except Exception as exc:
            log.warning("route_cache_redis_get_failed: %s", exc)
        return None

    def _redis_set(self, key: str, response: RouteResponse, ttl: int) -> None:
        try:
            import pickle
            self._redis.setex(f"synapse:route:{key}", ttl, pickle.dumps(response))
        except Exception as exc:
            log.warning("route_cache_redis_set_failed: %s", exc)

    def _redis_ttl(self, key: str) -> float:
        try:
            remaining = self._redis.ttl(f"synapse:route:{key}")
            return max(0.0, float(remaining))
        except Exception:
            return float(self._ttl)

    @classmethod
    def metrics(cls) -> dict[str, int]:
        return {
            "synapse_route_cache_hits_total": cls._hits_total,
            "synapse_route_cache_misses_total": cls._misses_total,
            "synapse_route_cache_invalidations_total": cls._invalidations_total,
        }


# ─────────────────────────────────────────────────────────────────────────────
# C3 — HeartbeatCache  (registry-side stub for SDK)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _HeartbeatEntry:
    response: HeartbeatResponse
    fetched_at: float  # time.monotonic() timestamp
    consecutive_failures: int = 0
    last_error: str | None = None

    def age_s(self) -> float:
        return time.monotonic() - self.fetched_at


class HeartbeatCache:
    """C3: In-process registry-side store of the most-recent HeartbeatResponse
    for each registered model.

    The routing engine reads exclusively from this cache; live heartbeat polls
    happen in a background thread and MUST NOT be triggered on the hot path
    (§8 C3 MUST NOT note).

    Staleness thresholds (configurable via env vars):

    * fresh      — age < stale_threshold_s (30 s default)
    * stale      — age in [stale_threshold_s, drop_threshold_s)
    * very_stale — age >= drop_threshold_s (90 s default)
    * unavailable — consecutive_failures >= 3
    """

    def __init__(
        self,
        stale_threshold_s: float | None = None,
        drop_threshold_s: float | None = None,
    ) -> None:
        self._stale_threshold: float = stale_threshold_s or float(
            os.getenv("SYNAPSE_HEARTBEAT_STALE_THRESHOLD_SECONDS", "30")
        )
        self._drop_threshold: float = drop_threshold_s or float(
            os.getenv("SYNAPSE_HEARTBEAT_DROP_THRESHOLD_SECONDS", "90")
        )
        self._store: dict[str, _HeartbeatEntry] = {}
        self._lock = threading.Lock()

    def store(self, response: HeartbeatResponse) -> None:
        """Record a fresh HeartbeatResponse (called by the background polling thread)."""
        entry = _HeartbeatEntry(response=response, fetched_at=time.monotonic())
        with self._lock:
            existing = self._store.get(response.model_id)
            if existing is not None:
                entry.consecutive_failures = 0  # successful poll resets failure counter
            self._store[response.model_id] = entry

    def get(self, model_id: str) -> HeartbeatResponse | None:
        """Return the cached HeartbeatResponse, or None if never polled."""
        with self._lock:
            entry = self._store.get(model_id)
        return entry.response if entry is not None else None

    def is_stale(self, model_id: str) -> bool:
        """True when the cached heartbeat data is older than stale_threshold_s."""
        with self._lock:
            entry = self._store.get(model_id)
        if entry is None:
            return True
        return entry.age_s() >= self._stale_threshold

    def record_failure(self, model_id: str, error: str) -> None:
        """Increment the failure counter for a model (called on poll error)."""
        with self._lock:
            entry = self._store.get(model_id)
            if entry is not None:
                entry.consecutive_failures += 1
                entry.last_error = error

    def get_routing_status(self, model_id: str) -> str:
        """Return routing confidence for a model: 'fresh' | 'stale' | 'very_stale' | 'unavailable' | 'unknown'."""
        with self._lock:
            entry = self._store.get(model_id)
        if entry is None:
            return "unknown"
        if entry.consecutive_failures >= 3:
            return "unavailable"
        age = entry.age_s()
        if age >= self._drop_threshold:
            return "very_stale"
        if age >= self._stale_threshold:
            return "stale"
        return "fresh"

    def metrics(self) -> dict[str, int]:
        with self._lock:
            entries = list(self._store.values())
        now = time.monotonic()
        stale = sum(1 for e in entries if (now - e.fetched_at) >= self._stale_threshold)
        unavailable = sum(
            1 for e in entries
            if (now - e.fetched_at) >= self._drop_threshold or e.consecutive_failures >= 3
        )
        return {
            "synapse_heartbeat_stale_count": stale,
            "synapse_heartbeat_unavailable_count": unavailable,
        }


# ─────────────────────────────────────────────────────────────────────────────
# C4 — ContextStore Protocol + three reference implementations
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class ContextStore(Protocol):
    """C4: Interface all context store implementations MUST satisfy (§8 C4).

    All methods MUST be safe to call concurrently.
    All methods MUST NOT raise — failures are logged and silently dropped so
    that a storage failure never gates a pipeline request.
    """

    def get(self, session_id: str, key: str) -> bytes | None:
        """Return stored bytes, or None if the key does not exist or has expired.
        MUST complete within 50 ms.
        """
        ...

    def set(
        self,
        session_id: str,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store bytes.  ttl_seconds=None inherits session TTL.
        MUST complete within 100 ms.
        """
        ...

    def delete(self, session_id: str, key: str) -> None:
        """Delete a specific key.  No-op if the key does not exist."""
        ...

    def expire_session(self, session_id: str) -> None:
        """Delete all keys for a session.  Called at session end.
        MUST complete within 500 ms.
        """
        ...


# ── InMemoryContextStore ──────────────────────────────────────────────────────

class InMemoryContextStore:
    """C4 InMemory: Development and testing only.

    WARNING: state is lost on process restart — not suitable for production.
    Thread-safe via threading.Lock.  LRU eviction at the session level when
    max_sessions is exceeded.
    """

    def __init__(
        self,
        session_ttl: int | None = None,
        max_sessions: int | None = None,
    ) -> None:
        self._session_ttl: int = session_ttl or int(
            os.getenv("SYNAPSE_CONTEXT_STORE_SESSION_TTL_SECONDS", "3600")
        )
        self._max_sessions: int = max_sessions or 1000
        # {session_id: {key: (value_bytes, absolute_expiry_monotonic)}}
        self._data: OrderedDict[str, dict[str, tuple[bytes, float]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, session_id: str, key: str) -> bytes | None:
        t0 = time.monotonic()
        try:
            with self._lock:
                session = self._data.get(session_id)
                if session is None:
                    return None
                entry = session.get(key)
                if entry is None:
                    return None
                value, expires_at = entry
                if time.monotonic() > expires_at:
                    del session[key]
                    return None
                # Sliding window: touch session on access
                self._data.move_to_end(session_id)
                return value
        except Exception as exc:
            log.warning("context_store_get_error: %s", exc)
            return None
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 50:
                log.warning("context_store_get_latency: %.1f ms exceeds 50 ms threshold", elapsed_ms)

    def set(
        self,
        session_id: str,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        t0 = time.monotonic()
        try:
            ttl = ttl_seconds if ttl_seconds is not None else self._session_ttl
            expires_at = time.monotonic() + ttl
            with self._lock:
                if session_id not in self._data:
                    self._evict_if_needed()
                    self._data[session_id] = {}
                self._data.move_to_end(session_id)
                self._data[session_id][key] = (value, expires_at)
        except Exception as exc:
            log.warning("context_store_set_error: %s", exc)
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 100:
                log.warning("context_store_set_latency: %.1f ms exceeds 100 ms threshold", elapsed_ms)

    def delete(self, session_id: str, key: str) -> None:
        try:
            with self._lock:
                session = self._data.get(session_id)
                if session is not None:
                    session.pop(key, None)
        except Exception as exc:
            log.warning("context_store_delete_error: %s", exc)

    def expire_session(self, session_id: str) -> None:
        try:
            with self._lock:
                self._data.pop(session_id, None)
        except Exception as exc:
            log.warning("context_store_expire_session_error: %s", exc)

    def _evict_if_needed(self) -> None:
        # caller holds self._lock
        while len(self._data) >= self._max_sessions:
            self._data.popitem(last=False)


# ── RedisContextStore ─────────────────────────────────────────────────────────

class RedisContextStore:
    """C4 Redis: Production context store backed by Redis.

    Keys are stored as ``synapse:ctx:{session_id}:{key}`` with native Redis TTL.
    On any Redis failure, get() returns None and set() logs a warning — the
    pipeline continues without context.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        session_ttl: int | None = None,
    ) -> None:
        url = redis_url or os.getenv("SYNAPSE_CONTEXT_STORE_REDIS_URL", "")
        if not url:
            raise ValueError(
                "SYNAPSE_CONTEXT_STORE_REDIS_URL is required for RedisContextStore"
            )
        self._session_ttl: int = session_ttl or int(
            os.getenv("SYNAPSE_CONTEXT_STORE_SESSION_TTL_SECONDS", "3600")
        )
        self._redis = self._connect(url)

    def _connect(self, url: str):
        try:
            import redis as _redis
            pool = _redis.ConnectionPool.from_url(url, max_connections=10)
            client = _redis.Redis(connection_pool=pool)
            client.ping()
            log.info("redis_context_store_connected: url=%s", url)
            return client
        except Exception as exc:
            log.warning("redis_context_store_connect_failed: %s — store will return None for all gets", exc)
            return None

    def _rkey(self, session_id: str, key: str) -> str:
        return f"synapse:ctx:{session_id}:{key}"

    def get(self, session_id: str, key: str) -> bytes | None:
        t0 = time.monotonic()
        try:
            if self._redis is None:
                return None
            return self._redis.get(self._rkey(session_id, key))  # raw bytes or None
        except Exception as exc:
            log.warning("redis_context_store_get_failed: %s", exc)
            return None
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 50:
                log.warning("context_store_get_latency: %.1f ms exceeds 50 ms threshold", elapsed_ms)

    def set(
        self,
        session_id: str,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        t0 = time.monotonic()
        try:
            if self._redis is None:
                return
            ttl = ttl_seconds if ttl_seconds is not None else self._session_ttl
            self._redis.setex(self._rkey(session_id, key), ttl, value)
        except Exception as exc:
            log.warning("redis_context_store_set_failed: %s", exc)
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 100:
                log.warning("context_store_set_latency: %.1f ms exceeds 100 ms threshold", elapsed_ms)

    def delete(self, session_id: str, key: str) -> None:
        try:
            if self._redis is not None:
                self._redis.delete(self._rkey(session_id, key))
        except Exception as exc:
            log.warning("redis_context_store_delete_failed: %s", exc)

    def expire_session(self, session_id: str) -> None:
        try:
            if self._redis is None:
                return
            pattern = f"synapse:ctx:{session_id}:*"
            cursor: int = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            log.warning("redis_context_store_expire_session_failed: %s", exc)


# ── S3ContextStore ────────────────────────────────────────────────────────────

class S3ContextStore:
    """C4 S3: Large-payload context store backed by Amazon S3.

    Suitable for payloads > 1 MB or pipelines with long duration.
    Latency: 50–200 ms per get/set — only suitable for non-latency-critical paths.

    Session expiry is managed by S3 Lifecycle rules applied to the key prefix.
    expire_session() performs a synchronous list-and-delete.
    """

    def __init__(
        self,
        bucket: str | None = None,
        prefix: str | None = None,
        session_ttl: int | None = None,
    ) -> None:
        self._bucket = bucket or os.getenv("SYNAPSE_CONTEXT_STORE_S3_BUCKET", "")
        if not self._bucket:
            raise ValueError(
                "SYNAPSE_CONTEXT_STORE_S3_BUCKET is required for S3ContextStore"
            )
        self._prefix = prefix or os.getenv("SYNAPSE_CONTEXT_STORE_S3_PREFIX", "synapse/ctx/")
        self._session_ttl: int = session_ttl or int(
            os.getenv("SYNAPSE_CONTEXT_STORE_SESSION_TTL_SECONDS", "3600")
        )
        self._s3 = self._connect()

    def _connect(self):
        try:
            import boto3  # optional dependency
            return boto3.client("s3")
        except Exception as exc:
            log.warning("s3_context_store_connect_failed: %s — store will return None for all gets", exc)
            return None

    def _s3key(self, session_id: str, key: str) -> str:
        return f"{self._prefix}{session_id}/{key}"

    def get(self, session_id: str, key: str) -> bytes | None:
        t0 = time.monotonic()
        try:
            if self._s3 is None:
                return None
            resp = self._s3.get_object(Bucket=self._bucket, Key=self._s3key(session_id, key))
            return resp["Body"].read()
        except Exception as exc:
            # NoSuchKey is a normal miss — only warn on unexpected errors
            if "NoSuchKey" not in type(exc).__name__:
                log.warning("s3_context_store_get_failed: %s", exc)
            return None
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 50:
                log.warning("context_store_get_latency: %.1f ms exceeds 50 ms threshold", elapsed_ms)

    def set(
        self,
        session_id: str,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        t0 = time.monotonic()
        try:
            if self._s3 is None:
                return
            self._s3.put_object(
                Bucket=self._bucket,
                Key=self._s3key(session_id, key),
                Body=value,
            )
        except Exception as exc:
            log.warning("s3_context_store_set_failed: %s", exc)
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 100:
                log.warning("context_store_set_latency: %.1f ms exceeds 100 ms threshold", elapsed_ms)

    def delete(self, session_id: str, key: str) -> None:
        try:
            if self._s3 is not None:
                self._s3.delete_object(Bucket=self._bucket, Key=self._s3key(session_id, key))
        except Exception as exc:
            log.warning("s3_context_store_delete_failed: %s", exc)

    def expire_session(self, session_id: str) -> None:
        try:
            if self._s3 is None:
                return
            prefix = f"{self._prefix}{session_id}/"
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                objects = page.get("Contents", [])
                if objects:
                    self._s3.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                    )
        except Exception as exc:
            log.warning("s3_context_store_expire_session_failed: %s", exc)


# ── Factory ───────────────────────────────────────────────────────────────────

def make_context_store() -> InMemoryContextStore | RedisContextStore | S3ContextStore:
    """Instantiate the context store selected by SYNAPSE_CONTEXT_STORE_BACKEND.

    ``memory`` (default) → InMemoryContextStore
    ``redis``            → RedisContextStore
    ``s3``               → S3ContextStore
    """
    backend = os.getenv("SYNAPSE_CONTEXT_STORE_BACKEND", "memory").lower()
    if backend == "redis":
        return RedisContextStore()
    if backend == "s3":
        return S3ContextStore()
    return InMemoryContextStore()


# ─────────────────────────────────────────────────────────────────────────────
# C5 — CalibrationBuffer
# ─────────────────────────────────────────────────────────────────────────────

def _run_with_timeout(timeout_s: float, fn, *args, **kwargs) -> Any:
    """Execute fn(*args, **kwargs) in a thread; raise TimeoutError if it stalls."""
    result: list[Any] = []
    exc_box: list[BaseException] = []

    def _target():
        try:
            result.append(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001
            exc_box.append(exc)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        raise TimeoutError(f"timed out after {timeout_s}s")
    if exc_box:
        raise exc_box[0]
    return result[0] if result else None


class CalibrationBuffer:
    """C5: Non-blocking calibration signal buffer with background flush thread.

    ``submit()`` MUST return in < 0.1 ms — it only appends to an in-process
    deque and MUST NOT make any network calls.

    A daemon thread flushes the buffer to the registry's
    ``POST /v1/calibration/signal`` endpoint every flush_interval seconds
    (default 5 s) or when the buffer reaches max_size.

    Overflow policy: drop-oldest, never drop-newest.  Every drop emits a
    WARNING log entry.

    An atexit hook attempts a final flush with a hard 2-second timeout; if
    the flush does not complete, remaining signals are dropped and the process
    is allowed to exit.

    Set SYNAPSE_CAL_ENABLED=false to discard all signals silently (air-gapped
    or cost-sensitive deployments).
    """

    def __init__(self, endpoint_url: str | None = None) -> None:
        self._enabled: bool = os.getenv("SYNAPSE_CAL_ENABLED", "true").lower() == "true"
        self._max_size: int = int(os.getenv("SYNAPSE_CAL_BUFFER_MAX", "100"))
        self._flush_interval: float = float(os.getenv("SYNAPSE_CAL_FLUSH_INTERVAL_SECONDS", "5"))
        self._max_retries: int = int(os.getenv("SYNAPSE_CAL_MAX_RETRIES", "3"))
        self._endpoint_url: str = (endpoint_url or os.getenv("SYNAPSE_REGISTRY_URL", "")).rstrip("/")

        self._buffer: deque[CalibrationSignal] = deque()
        self._lock = threading.Lock()
        self._signals_dropped: int = 0
        self._flush_failures: int = 0

        if self._enabled:
            self._flush_thread = threading.Thread(
                target=self._flush_loop,
                name="synapse-cal-flush",
                daemon=True,
            )
            self._flush_thread.start()
            atexit.register(self._shutdown_flush)

    # ── Public API ────────────────────────────────────────────────────────────

    def submit(self, signal: CalibrationSignal) -> None:
        """Non-blocking signal submission.

        MUST return in < 0.1 ms.
        MUST NOT make network calls.
        MUST NOT raise under any circumstances.
        """
        if not self._enabled:
            return
        try:
            with self._lock:
                if len(self._buffer) >= self._max_size:
                    self._buffer.popleft()  # drop oldest, keep newest
                    self._signals_dropped += 1
                    log.warning(
                        "calibration_buffer_overflow: signal dropped "
                        "max_size=%d total_dropped=%d",
                        self._max_size,
                        self._signals_dropped,
                    )
                self._buffer.append(signal)
        except Exception as exc:  # noqa: BLE001
            log.error("calibration_buffer_submit_failed: %s", exc)
            # swallow — never propagate to the calling pipeline

    # ── Background flush ──────────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        """Daemon thread: flush on interval until process exits."""
        while True:
            time.sleep(self._flush_interval)
            try:
                self._flush()
            except Exception as exc:  # noqa: BLE001
                log.error("calibration_flush_loop_error: %s", exc)

    def _flush(self) -> None:
        """Drain the buffer and send the batch.  Network I/O happens outside the lock."""
        with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()
        self._send_with_retry(batch)

    def _send_with_retry(self, batch: list[CalibrationSignal]) -> None:
        """Submit batch to the registry with exponential backoff (1 s, 2 s, 4 s)."""
        if not self._endpoint_url:
            log.debug(
                "calibration_flush_skipped: no endpoint configured, %d signals not sent",
                len(batch),
            )
            return

        backoff = [1.0, 2.0, 4.0]
        for attempt in range(self._max_retries):
            try:
                self._post_batch(batch)
                return
            except Exception as exc:  # noqa: BLE001
                if attempt < self._max_retries - 1:
                    delay = backoff[attempt]
                    log.warning(
                        "calibration_flush_retry: attempt=%d/%d delay=%.0fs error=%s",
                        attempt + 1,
                        self._max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    self._flush_failures += 1
                    log.error(
                        "calibration_flush_failed: dropped %d signals after %d attempts: %s",
                        len(batch),
                        self._max_retries,
                        exc,
                    )

    def _post_batch(self, batch: list[CalibrationSignal]) -> None:
        """HTTP POST of the signal batch to POST /v1/calibration/signal."""
        import json as _json
        import urllib.request

        payload = _json.dumps([
            {
                "model_id": s.model_id,
                "adapter_version": s.adapter_version,
                "task_type": s.task_type,
                "domain": s.domain,
                "latency_ms": s.latency_ms,
                "confidence": s.confidence,
                "timestamp_unix": s.timestamp_unix,
                "cost_usd": s.cost_usd,
                "token_count": s.token_count,
                "session_id": s.session_id,
                "pipeline_hop": s.pipeline_hop,
            }
            for s in batch
        ]).encode()

        url = f"{self._endpoint_url}/v1/calibration/signal"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"registry returned HTTP {resp.status}")

    # ── Graceful shutdown ─────────────────────────────────────────────────────

    def _shutdown_flush(self) -> None:
        """atexit hook: attempt a final flush with a 2-second hard timeout."""
        try:
            _run_with_timeout(2.0, self._flush)
        except TimeoutError:
            with self._lock:
                dropped = len(self._buffer)
            log.warning(
                "calibration_buffer_shutdown: %d signals dropped (2 s timeout exceeded)",
                dropped,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("calibration_buffer_shutdown_error: %s", exc)

    # ── Observability ─────────────────────────────────────────────────────────

    def metrics(self) -> dict[str, int]:
        with self._lock:
            size = len(self._buffer)
        return {
            "synapse_cal_buffer_size": size,
            "synapse_cal_signals_dropped_total": self._signals_dropped,
            "synapse_cal_flush_failures_total": self._flush_failures,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public re-exports
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # types
    "RouteCandidate",
    "RouteRequest",
    "RouteResponse",
    "HeartbeatResponse",
    "CalibrationSignal",
    # errors
    "AdapterLoadError",
    # C1
    "AdapterInstanceCache",
    # C2
    "RouteCacheClient",
    # C3
    "HeartbeatCache",
    # C4
    "ContextStore",
    "InMemoryContextStore",
    "RedisContextStore",
    "S3ContextStore",
    "make_context_store",
    # C5
    "CalibrationBuffer",
]
