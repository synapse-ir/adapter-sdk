# Security Requirements

This document describes the security design of the SYNAPSE Adapter SDK — the threat model it is built against and the specific controls the SDK enforces. For information on reporting a vulnerability, see [SECURITY.md](https://github.com/synapse-ir/adapter-sdk/blob/main/SECURITY.md).

---

## Threat Model

The SDK occupies a specific, narrow position: it is a Python library that runs inside a pipeline orchestrator process and mediates between that orchestrator and third-party AI model adapters. The primary threats are:

1. **Adapter exfiltration** — a malicious or compromised adapter exfiltrates IR payload data to an external endpoint during inference
2. **Pipeline state corruption** — an adapter modifies shared IR state (provenance chain, task header, compliance envelope) in a way that causes downstream adapters to operate on incorrect context
3. **Injection via IR payload** — user-supplied content in `payload.content` is misinterpreted as code or instructions by the SDK itself
4. **Dependency compromise** — a transitive dependency is compromised and introduces malicious behaviour into the SDK or any adapter that imports it

The SDK does not operate a server, handle authentication tokens, or process untrusted code execution at runtime. Threats such as SQL injection, XSS, and SSRF are not in scope.

---

## Control 1 — No Network Calls in Adapters (NO_NETWORK_CALLS)

**What it does:** The `AdapterValidator` enforces the `NO_NETWORK_CALLS` rule before any adapter can be published. It inspects adapter source code for imports of known network libraries: `requests`, `httpx`, `urllib`, `socket`, `aiohttp`, and others. An adapter that imports any of these in its `ingress` or `egress` path fails with a `MUST`-level error and is blocked from publication.

**Why it matters:** `ingress()` and `egress()` run inside the SDK process. A network call from within those functions would allow an adapter to exfiltrate IR payload content — including the full `payload.content` field and any structured data — to an arbitrary external endpoint. The purity requirement eliminates this exfiltration surface entirely.

**How data flows instead:** Adapters that need external context receive it via the IR itself. Callers pre-fetch any necessary context and pass it through `payload.data` or `payload.context_ref` before the pipeline hop. The `context_ref` pattern delegates external I/O to the SDK's C4 `ContextStore`, which operates with controlled credentials and a defined TTL.

---

## Control 2 — Input Validation via Pydantic

**What it does:** `CanonicalIR` and all nested types (`TaskHeader`, `Payload`, `ProvenanceEntry`, `ComplianceEnvelope`) are Pydantic models defined in `src/synapse_sdk/types.py`. Field types, ranges, and constraints are validated at construction time:

- `ir_version` must be a valid semver string
- `message_id` must be a valid UUID v4
- `confidence` fields must be in `[0.0, 1.0]`
- `latency_ms` must be `>= 0`
- `ADAPTER_VERSION` must be valid semver (`VERSION_SEMVER` rule)
- Null bytes in string fields are rejected (`IRInvalidFieldError`)
- Payload fields that exceed hard size limits raise `IRPayloadTooLargeError` before the IR is passed to any adapter

**Why it matters:** The IR carries user-supplied text in `payload.content`. Pydantic validation ensures that malformed or oversized inputs are rejected at the SDK boundary rather than propagated to adapters or the registry. There is no dynamic evaluation of payload content anywhere in the SDK.

---

## Control 3 — No Secrets in the IR

**What it does:** The `CanonicalIR` schema contains no fields for credentials, API keys, tokens, or passwords. The `ComplianceEnvelope` carries governance metadata (PII flags, data residency, retention policy) but not authentication material. The `payload.data` field accepts arbitrary structured data, but it is treated as opaque bytes — the SDK never reads, logs, or indexes its contents.

**Why it matters:** If the IR were to carry secrets, they would propagate through every pipeline hop, appear in provenance logs, and potentially be forwarded to calibration endpoints. By excluding credential fields from the schema, the SDK makes secret storage in the IR structurally impossible for well-typed adapters.

**Operational note:** Adapter manifests submitted to the registry must not include secrets. The registry stores manifest fields verbatim and serves them to any authenticated client.

---

## Control 4 — Dependency Pinning via uv.lock

**What it does:** All direct and transitive dependencies are pinned in `uv.lock`, which is committed to the repository. Builds are reproducible: `uv sync --frozen` installs exactly the versions recorded in the lock file and fails if any hash mismatches.

**Why it matters:** Unpinned dependencies allow a compromised upstream release to enter the build silently. `uv.lock` records exact versions and hashes; a tampered package will fail the hash check before it is installed.

---

## Control 5 — Dependabot for Automated CVE Tracking

**What it does:** Dependabot is configured on the `synapse-ir/adapter-sdk` repository to monitor PyPI dependencies and open pull requests when a dependency has a published CVE or a new version is available. PRs from Dependabot go through the same CI gate as all other PRs (ruff, mypy, full test suite, `synapse-validate` on all bundled adapters).

**Why it matters:** Even with pinned dependencies, new CVEs are published against already-pinned versions. Dependabot ensures that known-vulnerable versions are upgraded promptly rather than discovered during an audit.

---

## Summary

| Threat | Control | Enforcement point |
|--------|---------|-------------------|
| Adapter exfiltration | `NO_NETWORK_CALLS` rule | `AdapterValidator` at publish time |
| Pipeline state corruption | `PROVENANCE_IMMUTABLE`, `TASK_HEADER_CARRIED`, `COMPLIANCE_CARRIED` rules | `AdapterValidator` at publish time |
| Malformed / oversized input | Pydantic field validation + size limits | `CanonicalIR` constructor |
| Secrets in transit | No credential fields in IR schema | Structural (type system) |
| Dependency compromise | `uv.lock` pinning + Dependabot | CI and dependency management |

---

## Security review

**Date:** May 2026  
**Scope:** Full review of `src/synapse_sdk/` (validator, type system, cache layers, tracing, CLI, local-mode) and all CI/release infrastructure  
**Reviewer:** Chris Widmer (Founding Maintainer), with independent review of the threat model and control set as part of the OpenSSF Best Practices Gold badge assessment process  

The review examined each of the four threat categories above and confirmed that the five controls are correctly implemented and enforced. No critical or high-severity issues were identified. The following observations were recorded:

| Finding | Severity | Resolution |
|---------|----------|------------|
| `CalibrationBuffer` uses `urllib.request.urlopen` for calibration endpoint calls — intentional and limited to the SDK process, not adapter code | Informational | Documented in `S310` ruff ignore; `NO_NETWORK_CALLS` rule applies to adapter code only, not SDK internals |
| `payload.data` accepts arbitrary bytes — no content inspection | Informational | By design; SDK never deserialises or executes payload data |
| Signed releases use sigstore attestations via PyPI Trusted Publishing | Positive control | Verified in `.github/workflows/release.yml` |

This document will be updated after each major release cycle or when the threat model changes. A third-party security audit is planned as part of the LF AI & Data Foundation sandbox application process.
