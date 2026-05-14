# SYNAPSE Adapter SDK — Roadmap

This document describes planned direction for the SYNAPSE Adapter SDK over the next 12 months. Timelines are targets, not guarantees; they shift based on community feedback and maintainer capacity. Work that is not listed here is not planned — scope is deliberately narrow so that the adapter contract stays stable.

---

## Q3 2026 — Registry Integration and Async Adapters (July – September 2026)

### Registry Integration (GA)
- Publish the `RegistryClient` to PyPI as part of `synapse-adapter-sdk`
- Adapter manifests auto-registered on `synapse-validate --publish`
- `synapse-validate --all-fixtures` wired into the registry CI gate — adapters that regress on any fixture are blocked from re-publishing
- Registry heartbeat polling integrated with C3 `HeartbeatCache` out of the box

### Async Adapter Support
- `AsyncAdapterBase` abstract class with `async def ingress` / `async def egress` signatures
- `AdapterValidator` extended to run async behavioural rules under `asyncio`
- All 20 standard fixtures available as async-compatible test helpers
- Documentation and a reference async adapter (Whisper streaming) added to the ecosystem

### Developer Tooling
- `synapse-validate --watch` mode: re-runs all 13 rules on file save
- VS Code extension stub: inline rule failures in the editor gutter
- `AdapterInstanceCache` metrics exported in OpenMetrics format

---

## Q4 2026 — OpenTelemetry GA and Redis C2 Hardening (October – December 2026)

### OpenTelemetry GA
- `propagate_trace_context()` and `adapter_span()` (`src/synapse_sdk/tracing.py`) promoted from preview to stable API
- Native OTLP exporter — no third-party bridge required
- Span attributes aligned with OpenTelemetry Semantic Conventions for AI systems (draft)
- `SYNAPSE_OTEL_ENDPOINT` env var for zero-code configuration

### Redis C2 Hardening
- `RouteCacheClient` Redis L2 connection pooling with configurable pool size
- Redis cluster mode support (`redis://` and `rediss://` schemes)
- Automatic L2 eviction on model manifest updates via Redis pub/sub
- Circuit-breaker: three consecutive Redis failures → fallback to L1-only mode, self-healing on success

### Dependency and Supply Chain
- All pinned versions in `uv.lock` audited against current CVE database
- `uv audit` added to CI
- SBOM (CycloneDX JSON) generated on every release and attached to the GitHub release asset

---

## Q1 2027 — Python 3.14 Support and S3 Context Store GA (January – March 2027)

### Python 3.14 Support
- Full test matrix on CPython 3.14 (including free-threaded build)
- GIL-free compatibility audit for `AdapterInstanceCache` and `CalibrationBuffer`
- Deprecate Python 3.11 support (EOL October 2027); 3.12 minimum after 1.0

### S3 Context Store GA
- `S3ContextStore` (`src/synapse_sdk/cache.py`) promoted from preview to stable
- Multipart upload support for payloads > 100 MB
- Server-side encryption (SSE-S3 and SSE-KMS) configurable via `SYNAPSE_CONTEXT_STORE_S3_SSE`
- S3 Lifecycle rule template published for session-TTL management
- Integration tests against LocalStack included in CI

### IR Versioning
- `ir_version` negotiation: adapters declare minimum supported IR version in their manifest
- `CanonicalIR.migrate(target_version)` helper for forward-compatible pipelines
- Specification alignment with `github.com/synapse-ir/spec` v1.1

---

## Q2 2027 — 1.0 Stable Release (April – June 2027)

### 1.0 Stable Release
- All APIs marked `stable` frozen under semantic versioning — no breaking changes without a major version bump
- Full deprecation of any APIs tagged `preview` or `experimental` since 0.x
- 90%+ test coverage target (up from 80% at 0.x)
- Complete type-stub package (`synapse-adapter-sdk-stubs`) published to PyPI

### Ecosystem Completion
- 20 first-party adapters covering all `TaskType` values and all major `Domain` values
- Adapter certification program: third-party adapters can request a verified badge via `synapse-validate --publish --certify`
- Ecosystem index at `github.com/synapse-ir/ecosystem` with search by task type and domain

### OpenSSF Badge Gold
- Pursue OpenSSF Gold badge criteria: fuzzing, reproducible builds, static analysis clean
- Enable `pip audit` and `bandit` in CI
- Publish threat model document revision aligned with Gold requirements

---

## Out of Scope (for this period)

- A hosted inference API — SYNAPSE is an adapter contract layer, not an inference service
- Multi-language SDKs (Go, Rust) — the Python SDK is the reference implementation; community ports are welcome but not maintained here
- GUI tooling — the CLI and VS Code stub cover the target workflow
- Custom pipeline orchestration — SYNAPSE is composable into orchestrators; it does not ship one

---

*Last updated: May 2026. Maintained by: Chris Widmer (github.com/synapse-ir)*
