# Cache Layers

Five cache layers reduce per-hop overhead to approximately 1 ms in steady state. Each layer degrades gracefully — a cache miss or store failure falls through to the live computation and never causes a pipeline request to fail.

| Layer | Class | Location | Benefit |
|-------|-------|----------|---------|
| C1 | `AdapterInstanceCache` | SDK in-process | Eliminates module import overhead (~50–500 ms → ~0 ms) |
| C2 | `RouteCacheClient` | SDK in-process + optional Redis | Reduces routing query from 5–15 ms to < 0.5 ms |
| C3 | `HeartbeatCache` | Registry in-process | Prevents live polling on every route query |
| C4 | `ContextStore` | External (memory / Redis / S3) | Keeps IR payloads lean across pipeline hops |
| C5 | `CalibrationBuffer` | SDK in-process | Prevents blocking the hot path on network I/O |

Full specification: [github.com/synapse-ir/spec/s8-caching.md](https://github.com/synapse-ir/spec/blob/main/s8-caching.md)

---

## C1 — AdapterInstanceCache

Thread-safe in-process LRU cache of `AdapterBase` instances. Eliminates per-request module import cost.

**Key format:** `"{model_id}:{adapter_version}"`  
**Eviction:** LRU, no TTL — entries are permanent until explicit invalidation.  
**Default capacity:** 256 entries (`SYNAPSE_ADAPTER_CACHE_MAX`).

```python
from synapse_sdk import AdapterInstanceCache

# Register a factory before first use
AdapterInstanceCache.register(
    model_id="my-org/my-model-v1.0",
    version="1.0.0",
    factory=lambda: MyModelAdapter(),
)

# Retrieve (loads on first call, returns cached instance thereafter)
adapter = AdapterInstanceCache.get("my-org/my-model-v1.0", "1.0.0")

# Invalidate a specific entry (e.g. after a hot-swap)
AdapterInstanceCache.invalidate("my-org/my-model-v1.0", "1.0.0")

# Prometheus-compatible metrics
print(AdapterInstanceCache.metrics())
# {"synapse_adapter_cache_hits_total": 42, "synapse_adapter_cache_misses_total": 3, "size": 2}
```

| Method | Description |
|--------|-------------|
| `get(model_id, version)` | Return cached instance, loading if necessary. Raises `AdapterLoadError` on unresolvable model |
| `register(model_id, version, factory)` | Register a zero-arg callable that constructs the adapter |
| `invalidate(model_id, version)` | Remove a specific entry |
| `metrics()` | Return hit/miss/size counters |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_ADAPTER_CACHE_MAX` | `256` | Maximum cached instances |
| `SYNAPSE_ADAPTER_EAGER_LOAD` | `false` | Load all registered adapters at startup |

---

## C2 — RouteCacheClient

Two-tier routing decision cache. L1 is always in-process; L2 (Redis) is optional and shared across SDK instances.

**L1:** In-process LRU, ~0.01 ms lookup.  
**L2:** Redis, ~0.5–2 ms lookup, shared.  
**TTL:** 5–300 s, default 30 s. When L2 is present, L1 TTL is capped at `min(remaining_redis_ttl, 10s)`.

```python
from synapse_sdk import RouteCacheClient, RouteRequest, RouteResponse, RouteCandidate

cache = RouteCacheClient()

request = RouteRequest(
    task_type="classify",
    domain="medical",
    latency_budget_ms=500,
    compliance_tags=["hipaa"],
    quality_floor=0.8,
)

# Check cache
cached = cache.get(request)
if cached is None:
    # Miss — query the registry
    response = RouteResponse(candidates=[
        RouteCandidate(model_id="my-org/classifier", adapter_version="1.0.0", score=0.95),
    ])
    cache.set(request, response)

# Invalidate all entries containing a specific model (on manifest update)
cache.invalidate_model("my-org/classifier")

print(RouteCacheClient.metrics())
```

| Method | Description |
|--------|-------------|
| `get(request)` | Return cached `RouteResponse`, or `None` on miss |
| `set(request, response)` | Cache a routing decision |
| `invalidate(key)` | Evict a single entry by its pre-computed hash key |
| `invalidate_model(model_id)` | Evict all L1 entries that reference a model |
| `metrics()` | Return hit/miss/invalidation counters |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_ROUTE_CACHE_TTL_SECONDS` | `30` | TTL in seconds (clamped to 5–300) |
| `SYNAPSE_ROUTE_CACHE_MAX_ENTRIES` | `1000` | Maximum L1 entries |
| `SYNAPSE_ROUTE_CACHE_REDIS_URL` | *(none)* | Redis URL for L2 (e.g. `redis://localhost:6379`) |

---

## C3 — HeartbeatCache

Registry-side in-process store of the most-recent `HeartbeatResponse` for each model. The routing engine reads exclusively from this cache — live heartbeat polls happen in a background thread and are never triggered on the hot path.

```python
from synapse_sdk import HeartbeatCache, HeartbeatResponse

cache = HeartbeatCache()

# Background polling thread stores fresh responses
cache.store(HeartbeatResponse(
    model_id="my-org/classifier",
    status="available",
    capacity_pct=0.85,
    latency_p50_ms=43,
    latency_p99_ms=120,
    error_rate=0.002,
))

# Routing engine reads status without live polling
status = cache.get_routing_status("my-org/classifier")
# "fresh" | "stale" | "very_stale" | "unavailable" | "unknown"

# Check if data is stale (triggers background refresh, not inline poll)
if cache.is_stale("my-org/classifier"):
    trigger_background_poll()

# Record a poll failure
cache.record_failure("my-org/classifier", error="connection timeout")
```

| Method | Description |
|--------|-------------|
| `store(response)` | Record a fresh `HeartbeatResponse` |
| `get(model_id)` | Return cached response, or `None` if never polled |
| `is_stale(model_id)` | `True` when data is older than `stale_threshold_s` |
| `get_routing_status(model_id)` | `"fresh"` / `"stale"` / `"very_stale"` / `"unavailable"` / `"unknown"` |
| `record_failure(model_id, error)` | Increment failure counter; three consecutive failures → `"unavailable"` |
| `metrics()` | Return stale and unavailable counts |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_HEARTBEAT_STALE_THRESHOLD_SECONDS` | `30` | Age at which data is considered stale |
| `SYNAPSE_HEARTBEAT_DROP_THRESHOLD_SECONDS` | `90` | Age at which data is considered very_stale |

---

## C4 — ContextStore

Stores large or shared payload data outside the IR, referenced by `payload.context_ref`. Keeps the IR lean for transport while making large data available to downstream adapters.

Three implementations ship with the SDK. Select with `SYNAPSE_CONTEXT_STORE_BACKEND`.

```python
from synapse_sdk import make_context_store

# Auto-selects based on SYNAPSE_CONTEXT_STORE_BACKEND env var
store = make_context_store()

# Store bytes; ttl_seconds=None inherits session TTL
store.set(session_id="sess-abc", key="document", value=b"large payload bytes")

# Retrieve (returns None on miss or expiry)
data = store.get(session_id="sess-abc", key="document")

# Delete one key
store.delete(session_id="sess-abc", key="document")

# Delete all keys for a session (call at session end)
store.expire_session(session_id="sess-abc")
```

All methods are silent on failure — `get()` returns `None`, `set()` logs a warning. A storage failure never gates a pipeline request.

### InMemoryContextStore

Development and testing only. State is lost on process restart.

```python
from synapse_sdk import InMemoryContextStore

store = InMemoryContextStore(session_ttl=3600, max_sessions=1000)
```

### RedisContextStore

Production. Keys stored as `synapse:ctx:{session_id}:{key}` with native Redis TTL.

```python
from synapse_sdk import RedisContextStore

store = RedisContextStore(redis_url="redis://localhost:6379", session_ttl=3600)
# or set SYNAPSE_CONTEXT_STORE_REDIS_URL
```

### S3ContextStore

Large payloads or long-duration pipelines. Latency 50–200 ms per call — not suitable for latency-critical paths.

```python
from synapse_sdk import S3ContextStore

store = S3ContextStore(bucket="my-bucket", prefix="synapse/ctx/")
# or set SYNAPSE_CONTEXT_STORE_S3_BUCKET
```

Session expiry is managed by S3 Lifecycle rules on the key prefix. `expire_session()` performs a synchronous list-and-delete.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_CONTEXT_STORE_BACKEND` | `memory` | `memory` / `redis` / `s3` |
| `SYNAPSE_CONTEXT_STORE_SESSION_TTL_SECONDS` | `3600` | Default session TTL |
| `SYNAPSE_CONTEXT_STORE_REDIS_URL` | *(none)* | Redis URL for `RedisContextStore` |
| `SYNAPSE_CONTEXT_STORE_S3_BUCKET` | *(none)* | S3 bucket for `S3ContextStore` |
| `SYNAPSE_CONTEXT_STORE_S3_PREFIX` | `synapse/ctx/` | S3 key prefix |

---

## C5 — CalibrationBuffer

Non-blocking buffer that collects per-hop performance signals and flushes them to the registry in the background. `submit()` must return in < 0.1 ms — it only appends to an in-process deque.

```python
from synapse_sdk import CalibrationBuffer, CalibrationSignal

buffer = CalibrationBuffer(endpoint_url="https://registry.example.com")

# Submit a signal after each egress call — non-blocking
buffer.submit(CalibrationSignal(
    model_id="my-org/classifier",
    adapter_version="1.0.0",
    task_type="classify",
    domain="medical",
    latency_ms=43,
    confidence=0.94,
    cost_usd=0.00009,
    token_count=512,
    session_id="sess-abc",
    pipeline_hop=0,
))

print(buffer.metrics())
# {"synapse_cal_buffer_size": 3, "synapse_cal_signals_dropped_total": 0, "synapse_cal_flush_failures_total": 0}
```

The background flush thread sends signals to `POST /v1/calibration/signal` every 5 seconds (configurable), with exponential backoff retries (1 s, 2 s, 4 s). On overflow, the oldest signal is dropped — never the newest.

An `atexit` hook flushes remaining signals with a 2-second timeout on process exit.

| Method | Description |
|--------|-------------|
| `submit(signal)` | Non-blocking signal submission. Never raises. |
| `metrics()` | Buffer size, total dropped, total flush failures |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_CAL_ENABLED` | `true` | Set to `false` to discard all signals silently |
| `SYNAPSE_CAL_BUFFER_MAX` | `100` | Maximum buffered signals before drop-oldest eviction |
| `SYNAPSE_CAL_FLUSH_INTERVAL_SECONDS` | `5` | Background flush interval |
| `SYNAPSE_CAL_MAX_RETRIES` | `3` | Retry attempts before dropping a batch |
| `SYNAPSE_REGISTRY_URL` | *(none)* | Registry endpoint URL |
