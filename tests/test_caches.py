"""Tests for synapse_sdk.cache — §8 C1–C5."""

import time

import pytest

from synapse_sdk.cache import (
    AdapterInstanceCache,
    AdapterLoadError,
    CalibrationBuffer,
    CalibrationSignal,
    HeartbeatCache,
    HeartbeatResponse,
    InMemoryContextStore,
    RouteCacheClient,
    RouteCandidate,
    RouteRequest,
    RouteResponse,
    _route_cache_key,
    _run_with_timeout,
    make_context_store,
)

# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _signal(model_id: str = "m1") -> CalibrationSignal:
    return CalibrationSignal(
        model_id=model_id,
        adapter_version="1.0.0",
        task_type="classify",
        domain="general",
        latency_ms=50,
        confidence=0.9,
    )


def _route_req(**overrides) -> RouteRequest:
    return RouteRequest(
        task_type=overrides.get("task_type", "classify"),
        domain=overrides.get("domain", "legal"),
        latency_budget_ms=overrides.get("latency_budget_ms", 500),
        compliance_tags=overrides.get("compliance_tags"),
    )


def _route_resp(*model_ids: str) -> RouteResponse:
    return RouteResponse(
        candidates=[
            RouteCandidate(model_id=m, adapter_version="1.0.0", score=0.9)
            for m in model_ids
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers / utilities
# ──────────────────────────────────────────────────────────────────────────────

class TestRunWithTimeout:

    def test_returns_result_of_fn(self):
        result = _run_with_timeout(1.0, lambda: 42)
        assert result == 42

    def test_propagates_exception_from_fn(self):
        def bad():
            raise ValueError("oops")
        with pytest.raises(ValueError, match="oops"):
            _run_with_timeout(1.0, bad)

    def test_raises_timeout_error_when_fn_stalls(self):
        import time as _time
        with pytest.raises(TimeoutError):
            _run_with_timeout(0.05, _time.sleep, 10)

    def test_returns_none_when_fn_returns_nothing(self):
        result = _run_with_timeout(1.0, lambda: None)
        assert result is None


class TestMakeContextStore:

    def test_default_backend_returns_in_memory(self, monkeypatch):
        monkeypatch.delenv("SYNAPSE_CONTEXT_STORE_BACKEND", raising=False)
        store = make_context_store()
        assert isinstance(store, InMemoryContextStore)

    def test_memory_backend_explicit(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CONTEXT_STORE_BACKEND", "memory")
        store = make_context_store()
        assert isinstance(store, InMemoryContextStore)


# ──────────────────────────────────────────────────────────────────────────────
# C1 — AdapterInstanceCache
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def clean_adapter_cache():
    """Reset AdapterInstanceCache class-level mutable state around each test."""
    AdapterInstanceCache._cache.clear()
    AdapterInstanceCache._registry.clear()
    yield
    AdapterInstanceCache._cache.clear()
    AdapterInstanceCache._registry.clear()


class TestAdapterInstanceCache:

    def test_get_raises_for_unknown_key(self, clean_adapter_cache):
        with pytest.raises(AdapterLoadError):
            AdapterInstanceCache.get("ghost-model", "9.9.9")

    def test_register_and_get_roundtrip(self, clean_adapter_cache):
        sentinel = object()
        AdapterInstanceCache.register("mdl", "1.0.0", lambda: sentinel)
        assert AdapterInstanceCache.get("mdl", "1.0.0") is sentinel

    def test_invalidate_removes_entry(self, clean_adapter_cache):
        AdapterInstanceCache.register("mdl", "1.0.0", lambda: object())
        AdapterInstanceCache.get("mdl", "1.0.0")
        assert "mdl:1.0.0" in AdapterInstanceCache._cache

        AdapterInstanceCache.invalidate("mdl", "1.0.0")
        assert "mdl:1.0.0" not in AdapterInstanceCache._cache

    def test_get_returns_cached_instance_on_second_call(self, clean_adapter_cache):
        sentinel = object()
        AdapterInstanceCache.register("mdl", "1.0.0", lambda: sentinel)
        first = AdapterInstanceCache.get("mdl", "1.0.0")
        second = AdapterInstanceCache.get("mdl", "1.0.0")  # cache hit path
        assert first is second is sentinel

    def test_metrics_returns_counters(self, clean_adapter_cache):
        AdapterInstanceCache.register("mdl", "1.0.0", lambda: object())
        AdapterInstanceCache.get("mdl", "1.0.0")  # miss
        AdapterInstanceCache.get("mdl", "1.0.0")  # hit
        m = AdapterInstanceCache.metrics()
        assert m["synapse_adapter_cache_hits_total"] >= 1
        assert m["synapse_adapter_cache_misses_total"] >= 1

    def test_lru_eviction_drops_oldest_entry(self, clean_adapter_cache):
        original_max = AdapterInstanceCache._max
        AdapterInstanceCache._max = 2
        try:
            for name in ("m1", "m2", "m3"):
                AdapterInstanceCache.register(name, "1.0", lambda n=name: n)
            AdapterInstanceCache.get("m1", "1.0")
            AdapterInstanceCache.get("m2", "1.0")
            # Cache is full (2 entries). Getting m3 evicts the oldest (m1).
            AdapterInstanceCache.get("m3", "1.0")

            assert "m1:1.0" not in AdapterInstanceCache._cache
            assert "m2:1.0" in AdapterInstanceCache._cache
            assert "m3:1.0" in AdapterInstanceCache._cache
        finally:
            AdapterInstanceCache._max = original_max


# ──────────────────────────────────────────────────────────────────────────────
# C2 — RouteCacheClient
# ──────────────────────────────────────────────────────────────────────────────

class TestRouteCacheClient:

    def test_l1_lru_eviction_on_set(self):
        """_l1_set eviction path (lines 341, 343) — fill to max then overflow."""
        client = RouteCacheClient()
        client._max = 2
        req1 = _route_req(task_type="classify", domain="legal")
        req2 = _route_req(task_type="embed", domain="finance")
        req3 = _route_req(task_type="generate", domain="medical")
        client.set(req1, _route_resp("m1"))
        client.set(req2, _route_resp("m2"))
        client.set(req3, _route_resp("m3"))  # evicts oldest
        with client._lock:
            assert len(client._l1) == 2

    def test_set_existing_key_moves_to_end(self):
        """_l1_set re-inserts existing key (line 341 branch)."""
        client = RouteCacheClient()
        req = _route_req()
        client.set(req, _route_resp("m1"))
        client.set(req, _route_resp("m2"))  # update existing key
        assert client.get(req).candidates[0].model_id == "m2"

    def test_metrics_returns_counters(self):
        """RouteCacheClient.metrics() (line 386)."""
        client = RouteCacheClient()
        m = client.metrics()
        assert "synapse_route_cache_hits_total" in m
        assert "synapse_route_cache_misses_total" in m
        assert "synapse_route_cache_invalidations_total" in m

    def test_key_construction_is_deterministic(self):
        req = _route_req()
        assert _route_cache_key(req) == _route_cache_key(req)

    def test_sorted_compliance_tags_produce_same_key(self):
        req_a = _route_req(compliance_tags=["pii", "gdpr"])
        req_b = _route_req(compliance_tags=["gdpr", "pii"])
        assert _route_cache_key(req_a) == _route_cache_key(req_b)

    def test_get_returns_none_on_cache_miss(self):
        client = RouteCacheClient()
        assert client.get(_route_req(task_type="embed", domain="finance")) is None

    def test_set_and_get_roundtrip(self):
        client = RouteCacheClient()
        req = _route_req()
        resp = _route_resp("target-model")
        client.set(req, resp)
        cached = client.get(req)
        assert cached is not None
        assert cached.candidates[0].model_id == "target-model"

    def test_invalidate_model_removes_entries_containing_that_model(self):
        client = RouteCacheClient()
        req = _route_req()
        client.set(req, _route_resp("target-model", "other-model"))
        assert client.get(req) is not None

        client.invalidate_model("target-model")
        assert client.get(req) is None

    def test_l1_entry_remaining_ttl_positive(self):
        from synapse_sdk.cache import _L1Entry
        entry = _L1Entry(_route_resp("m"), ttl=60)
        assert entry.remaining_ttl() > 0


# ──────────────────────────────────────────────────────────────────────────────
# C3 — HeartbeatCache
# ──────────────────────────────────────────────────────────────────────────────

class TestHeartbeatCache:

    def test_store_and_retrieve_by_model_id(self):
        cache = HeartbeatCache()
        cache.store(HeartbeatResponse(model_id="mdl", status="available", capacity_pct=0.85))
        result = cache.get("mdl")
        assert result is not None
        assert result.model_id == "mdl"
        assert result.status == "available"

    def test_is_stale_false_for_fresh_entry(self):
        cache = HeartbeatCache(stale_threshold_s=30)
        cache.store(HeartbeatResponse(model_id="fresh", status="available"))
        assert cache.is_stale("fresh") is False

    def test_is_stale_true_after_threshold_passes(self):
        cache = HeartbeatCache(stale_threshold_s=0.02)
        cache.store(HeartbeatResponse(model_id="old", status="available"))
        time.sleep(0.05)
        assert cache.is_stale("old") is True

    def test_is_stale_true_for_unknown_model(self):
        """is_stale returns True when model has never been stored (line 458)."""
        cache = HeartbeatCache()
        assert cache.is_stale("ghost-model") is True

    def test_store_twice_resets_failure_counter(self):
        """Second store resets consecutive_failures to 0 (line 444)."""
        cache = HeartbeatCache()
        cache.store(HeartbeatResponse(model_id="m", status="available"))
        with cache._lock:
            cache._store["m"].consecutive_failures = 3
        cache.store(HeartbeatResponse(model_id="m", status="available"))
        with cache._lock:
            assert cache._store["m"].consecutive_failures == 0

    def test_record_failure_increments_counter(self):
        """record_failure increments consecutive_failures (lines 463-467)."""
        cache = HeartbeatCache()
        cache.store(HeartbeatResponse(model_id="m", status="available"))
        cache.record_failure("m", "timeout")
        with cache._lock:
            assert cache._store["m"].consecutive_failures == 1
            assert cache._store["m"].last_error == "timeout"

    def test_record_failure_noop_for_unknown_model(self):
        """record_failure is silent for unknown model (no-op branch)."""
        cache = HeartbeatCache()
        cache.record_failure("ghost", "err")  # must not raise

    def test_get_routing_status_all_states(self):
        """get_routing_status covers fresh/stale/very_stale/unavailable/unknown."""
        cache = HeartbeatCache(stale_threshold_s=100, drop_threshold_s=200)
        assert cache.get_routing_status("ghost") == "unknown"

        cache.store(HeartbeatResponse(model_id="m", status="available"))
        assert cache.get_routing_status("m") == "fresh"

        with cache._lock:
            cache._store["m"].consecutive_failures = 3
        assert cache.get_routing_status("m") == "unavailable"

        cache2 = HeartbeatCache(stale_threshold_s=0.01, drop_threshold_s=100)
        cache2.store(HeartbeatResponse(model_id="m2", status="available"))
        time.sleep(0.05)
        assert cache2.get_routing_status("m2") == "stale"

        cache3 = HeartbeatCache(stale_threshold_s=0.01, drop_threshold_s=0.02)
        cache3.store(HeartbeatResponse(model_id="m3", status="available"))
        time.sleep(0.05)
        assert cache3.get_routing_status("m3") == "very_stale"

    def test_metrics(self):
        """HeartbeatCache.metrics() covers lines 485-493."""
        cache = HeartbeatCache(stale_threshold_s=100, drop_threshold_s=200)
        cache.store(HeartbeatResponse(model_id="m1", status="available"))
        m = cache.metrics()
        assert "synapse_heartbeat_stale_count" in m
        assert "synapse_heartbeat_unavailable_count" in m


# ──────────────────────────────────────────────────────────────────────────────
# C4 — InMemoryContextStore
# ──────────────────────────────────────────────────────────────────────────────

class TestInMemoryContextStore:

    def test_get_returns_none_for_missing_key(self):
        store = InMemoryContextStore()
        assert store.get("sess-1", "no-such-key") is None

    def test_set_and_get_roundtrip(self):
        store = InMemoryContextStore()
        store.set("sess-1", "mykey", b"hello bytes")
        assert store.get("sess-1", "mykey") == b"hello bytes"

    def test_delete_removes_key(self):
        store = InMemoryContextStore()
        store.set("sess-1", "k", b"data")
        store.delete("sess-1", "k")
        assert store.get("sess-1", "k") is None

    def test_expire_session_removes_all_keys_for_that_session(self):
        store = InMemoryContextStore()
        store.set("sess-a", "k1", b"v1")
        store.set("sess-a", "k2", b"v2")
        store.set("sess-b", "k3", b"v3")

        store.expire_session("sess-a")

        assert store.get("sess-a", "k1") is None
        assert store.get("sess-a", "k2") is None
        assert store.get("sess-b", "k3") == b"v3"  # unaffected session

    def test_lru_session_eviction(self):
        """_evict_if_needed drops oldest session when max_sessions is exceeded (line 632)."""
        store = InMemoryContextStore(max_sessions=2)
        store.set("s1", "k", b"v")
        store.set("s2", "k", b"v")
        store.set("s3", "k", b"v")  # triggers eviction of s1
        with store._lock:
            assert "s1" not in store._data
            assert "s3" in store._data

    def test_ttl_expiry_removes_key(self):
        """Expired key returns None (line 576-577 in get)."""
        store = InMemoryContextStore(session_ttl=3600)
        store.set("sess", "k", b"v", ttl_seconds=1)
        # Force expiry by setting the stored expiry in the past
        with store._lock:
            store._data["sess"]["k"] = (b"v", 0.0)
        assert store.get("sess", "k") is None


# ──────────────────────────────────────────────────────────────────────────────
# C5 — CalibrationBuffer
# ──────────────────────────────────────────────────────────────────────────────

class TestCalibrationBuffer:

    def test_submit_returns_within_100ms(self):
        buf = CalibrationBuffer()
        t0 = time.monotonic()
        buf.submit(_signal())
        assert (time.monotonic() - t0) * 1000 < 100

    def test_buffer_accepts_signals_up_to_max_size(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CAL_BUFFER_MAX", "5")
        monkeypatch.setenv("SYNAPSE_CAL_FLUSH_INTERVAL_SECONDS", "3600")
        buf = CalibrationBuffer()
        for i in range(5):
            buf.submit(_signal(model_id=f"m{i}"))
        with buf._lock:
            assert len(buf._buffer) == 5

    def test_overflow_drops_oldest_not_newest(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CAL_BUFFER_MAX", "3")
        monkeypatch.setenv("SYNAPSE_CAL_FLUSH_INTERVAL_SECONDS", "3600")
        buf = CalibrationBuffer()
        for i in range(3):
            buf.submit(_signal(model_id=f"m{i}"))
        buf.submit(_signal(model_id="newest"))
        with buf._lock:
            ids = [s.model_id for s in buf._buffer]
        assert "m0" not in ids
        assert "newest" in ids

    def test_disabled_via_env_discards_signals_silently(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CAL_ENABLED", "false")
        buf = CalibrationBuffer()
        buf.submit(_signal())
        with buf._lock:
            assert len(buf._buffer) == 0

    def test_metrics(self):
        """CalibrationBuffer.metrics() covers lines 1056-1058."""
        buf = CalibrationBuffer()
        buf.submit(_signal())
        m = buf.metrics()
        assert "synapse_cal_buffer_size" in m
        assert m["synapse_cal_buffer_size"] >= 1
        assert "synapse_cal_signals_dropped_total" in m
        assert "synapse_cal_flush_failures_total" in m
