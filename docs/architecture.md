# Architecture

This document describes the internal architecture of the SYNAPSE Adapter SDK: the five-layer cache stack, the adapter contract, the canonical IR format, and the local development mode.

---

## Overview

The SDK sits between a pipeline orchestrator and the model it is calling. Its job is narrow: accept a `CanonicalIR`, route it to the right adapter instance, pass the result through the adapter's `ingress`/`egress` pair, and return an updated `CanonicalIR` with a new `ProvenanceEntry` appended. Every layer of the SDK is designed so that a cache miss or an infrastructure failure degrades gracefully — the pipeline still completes, just without the performance benefit of the cache.

---

## Data Flow Through a Pipeline Hop

```
Caller / Orchestrator
         │
         ▼
┌────────────────────┐
│  C2 RouteCacheClient│◄──────┐
│  (in-process + Redis│       │ registry
│   L2, optional)     │       │ lookup on
└────────┬───────────┘       │ cache miss
         │                   │
         │                   ▼
         │          ┌──────────────────┐
         │          │ C3 HeartbeatCache │
         │          │ (registry-side;  │
         │          │  background poll) │
         │          └──────────────────┘
         │
         ▼
┌────────────────────┐
│ C1 AdapterInstance  │
│     Cache           │  ← module import on first call only
└────────┬───────────┘
         │
         ▼
  adapter.ingress(ir) ──────────────────────────────────────┐
         │                                                   │
         │  (optional) payload.context_ref resolved via      │
         │  ┌─────────────────┐                              │
         └─►│  C4 ContextStore │ (memory / Redis / S3)       │
            └─────────────────┘                              │
                                                             │
         ▼                                                   │
   Model Inference (external — outside the SDK)             │
         │                                                   │
         ▼                                                   │
  adapter.egress(output, original_ir, latency_ms) ◄─────────┘
         │
         │  ProvenanceEntry appended (immutable)
         │  task_header and compliance_envelope carried unchanged
         │
         ▼
   CanonicalIR (updated)
         │
         ▼
┌────────────────────┐
│  C5 CalibrationBuf │  ← non-blocking; < 0.1 ms submit()
│  (background flush)│
└────────────────────┘
         │
         ▼
   Response to Caller
```

The orchestrator sees only the first and last arrow. Everything between is SDK-internal.

---

## The Five-Layer Cache Stack

Defined in `src/synapse_sdk/cache.py`. Each layer is independent; failing one does not affect the others.

### C1 — AdapterInstanceCache

Thread-safe in-process LRU of `AdapterBase` instances keyed by `"{model_id}:{adapter_version}"`. Eliminates the 50–500 ms Python module import cost after the first call. Default capacity: 256 entries (`SYNAPSE_ADAPTER_CACHE_MAX`). Eviction is LRU with no TTL; entries are permanent until `invalidate()` is called explicitly (for example, on a hot-swap).

### C2 — RouteCacheClient

Two-tier routing decision cache. The L1 tier is always in-process (LRU, ~0.01 ms). The optional L2 tier uses Redis and is shared across SDK instances (~0.5–2 ms). The cache key is a hash of the `RouteRequest` fields; TTL defaults to 30 s and is clamped to 5–300 s. When L2 is present, L1 TTL is capped at `min(remaining_redis_ttl, 10 s)` so entries expire consistently across processes. L2 is enabled by setting `SYNAPSE_ROUTE_CACHE_REDIS_URL`.

### C3 — HeartbeatCache

Lives in the registry process, not in the SDK. The routing engine reads exclusively from this cache — it never makes a live heartbeat poll on the hot path. A background thread polls each registered model and calls `cache.store(response)`. Three consecutive poll failures transition a model to `"unavailable"` routing status. Relevant env vars: `SYNAPSE_HEARTBEAT_STALE_THRESHOLD_SECONDS` (default 30 s) and `SYNAPSE_HEARTBEAT_DROP_THRESHOLD_SECONDS` (default 90 s).

### C4 — ContextStore

Stores large payload data outside the IR, referenced by `payload.context_ref`. Keeps the IR lean for transport. Three implementations are provided: `InMemoryContextStore` (development only), `RedisContextStore` (production default), and `S3ContextStore` (large payloads or long-duration pipelines). Selected via `SYNAPSE_CONTEXT_STORE_BACKEND`. All methods are silent on failure — `get()` returns `None` and `set()` logs a warning rather than raising. A store failure never blocks a pipeline request.

### C5 — CalibrationBuffer

Non-blocking in-process deque that collects per-hop performance signals (`latency_ms`, `confidence`, `cost_usd`, `token_count`) and flushes them to the registry in the background. `submit()` is guaranteed to return in < 0.1 ms — it only appends to the deque. The background flush thread sends batches to `POST /v1/calibration/signal` every 5 s with exponential backoff (1 s, 2 s, 4 s). On overflow, the oldest signal is dropped. An `atexit` hook flushes remaining signals on process exit.

---

## The Adapter Contract

Every adapter extends `AdapterBase` (defined in `src/synapse_sdk/`) and implements exactly two methods.

### `ingress(ir: CanonicalIR) -> dict`

Converts the canonical IR into whatever format the underlying model natively expects. Must be a pure function:

- No network calls
- No persistent state mutations
- Must return a non-`None` value (even for empty inputs — return an empty dict rather than `None`)

The return value is passed directly to the model as its input.

### `egress(output: Any, original_ir: CanonicalIR, latency_ms: int) -> CanonicalIR`

Converts the model's raw output back to a `CanonicalIR` and appends exactly one `ProvenanceEntry`. Must also be a pure function, with the same constraints as `ingress`. Additional invariants:

- Always call `original_ir.clone()` — never `copy()` — to avoid sharing the provenance list
- Never modify any existing `ProvenanceEntry` (they are immutable at the type level)
- Carry `task_header` and `compliance_envelope` unchanged via `clone()`
- Append exactly one entry via `self.build_provenance(confidence=..., latency_ms=...)`

**Purity requirement rationale:** Adapters run inside the SDK process, which may be shared across tenants or pipeline sessions. A network call inside `ingress` or `egress` would break isolation, introduce latency variance, and create an exfiltration surface. The `NO_NETWORK_CALLS` validation rule enforces this at publish time by inspecting adapter source code for imports of network libraries.

---

## The Canonical IR Format

Defined in `src/synapse_sdk/types.py`. The `CanonicalIR` is the single data structure that flows through every pipeline hop. Its six top-level fields are:

| Field | Role |
|-------|------|
| `ir_version` | Semver string — enables forward-compatible migration |
| `message_id` | UUID v4 — unique per IR instance, never reused |
| `task_header` | Routing and scheduling metadata; immutable across hops |
| `payload` | The data being processed; adapters write their output here |
| `provenance` | Append-only audit chain; each hop adds one entry |
| `compliance_envelope` | PII and data governance flags; immutable across hops |

The `payload` field supports four modalities: `text`, `embedding`, `structured`, and `binary`. Large payloads should be stored via C4 `ContextStore` and referenced with `payload.context_ref` to keep the IR lean for transport.

`ProvenanceEntry` objects are immutable: field assignment raises `TypeError` at runtime. The `PROVENANCE_IMMUTABLE` and `PROVENANCE_APPENDED` validation rules enforce correct append-only behaviour before an adapter can be published.

---

## Local Development Mode

Set `SYNAPSE_LOCAL_MODE=1` to run the SDK without a live registry. In local mode (`src/synapse_sdk/local.py`):

- `RouteCacheClient` returns a configurable static `RouteResponse` instead of querying the registry
- `HeartbeatCache` reports all models as `"fresh"` without background polling
- `CalibrationBuffer` discards signals silently (equivalent to `SYNAPSE_CAL_ENABLED=false`)
- `ContextStore` defaults to `InMemoryContextStore` regardless of `SYNAPSE_CONTEXT_STORE_BACKEND`

Local mode is intended for adapter development and integration testing. It is detected automatically in `pytest` sessions when no `SYNAPSE_REGISTRY_URL` is configured.

---

## Distributed Tracing

Defined in `src/synapse_sdk/tracing.py`. The SDK propagates W3C Trace Context through the `task_header.trace_context` field of the IR. `propagate_trace_context(ir)` either reads an existing `traceparent` from the IR or synthesises a new root trace. `adapter_span(ir, adapter)` is a context manager that opens a child span for each `ingress`/`egress` pair and writes span attributes to the current OpenTelemetry tracer.

Tracing is opt-in: if no OpenTelemetry SDK is configured, the helpers are no-ops.

---

## Source Module Map

| Module | Responsibility |
|--------|---------------|
| `src/synapse_sdk/types.py` | `CanonicalIR`, `TaskHeader`, `Payload`, `ProvenanceEntry`, `ComplianceEnvelope`, and all supporting types |
| `src/synapse_sdk/cache.py` | `AdapterInstanceCache` (C1), `RouteCacheClient` (C2), `HeartbeatCache` (C3), `ContextStore` implementations (C4), `CalibrationBuffer` (C5) |
| `src/synapse_sdk/local.py` | `SYNAPSE_LOCAL_MODE` stubs — registry-free development |
| `src/synapse_sdk/tracing.py` | W3C Trace Context propagation and OpenTelemetry span helpers |
