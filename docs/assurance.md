# Assurance Case

This document presents the assurance case for the SYNAPSE Adapter SDK. An assurance case is a structured argument that a system achieves a specific safety or security goal, supported by concrete evidence. The structure used here is: **Goal → Strategy → Claims → Evidence**.

---

## Top-Level Goal

> **Adapters published via this SDK do not corrupt pipeline state or exfiltrate data.**

This goal covers the two primary failure modes for an adapter ecosystem: an adapter that silently modifies shared IR state causing downstream adapters to operate on incorrect context, and an adapter that sends IR payload content to an external endpoint the pipeline operator did not authorise.

---

## Strategy

The goal is decomposed into four claims, each addressing a distinct failure mode. Each claim is enforced by the SDK at publish time (via `AdapterValidator`) and verified continuously by the test suite. No claim relies solely on documentation or developer discipline — each has a machine-checked enforcement point.

---

## Claim 1 — Adapters cannot exfiltrate data

**Argument:** Any adapter that performs a network call from within `ingress()` or `egress()` is blocked from publication.

**Evidence:**

- The `NO_NETWORK_CALLS` rule (`AdapterValidator`, rule 7 of 13) inspects adapter source code for imports of network libraries (`requests`, `httpx`, `urllib`, `socket`, `aiohttp`) and fails with `Severity.MUST` if any are found.
- `synapse-validate --adapter <module>` enforces this rule in CI before any PR is merged.
- The validator test suite includes cases that confirm network-importing adapters are rejected and pure adapters pass. Test coverage of the validator is included in the project's ≥ 80% coverage threshold.
- See: [AdapterValidator reference](reference/validator.md) → `NO_NETWORK_CALLS`; [Security Requirements](security.md) → Control 1.

---

## Claim 2 — Adapters cannot corrupt the provenance chain

**Argument:** An adapter cannot modify, reorder, or delete existing `ProvenanceEntry` objects. It can only append exactly one new entry per `egress()` call.

**Evidence:**

- `ProvenanceEntry` objects are immutable at the type level: field assignment raises `TypeError` at runtime.
- Four `MUST`-level validation rules enforce correct provenance behaviour:
    - `PROVENANCE_APPENDED` — `egress()` must append exactly one entry
    - `PROVENANCE_IMMUTABLE` — `egress()` must not modify any pre-existing entry
    - `CONFIDENCE_RANGE` — the appended entry's `confidence` must be in `[0.0, 1.0]`
    - `MODEL_ID_MATCH` — the appended entry's `model_id` must match `adapter.MODEL_ID`
- All four rules are exercised against each of the 20 standard fixtures during `synapse-validate --all-fixtures`.
- See: [AdapterValidator reference](reference/validator.md) → rules table; [Canonical IR reference](reference/canonical-ir.md) → ProvenanceEntry.

---

## Claim 3 — Pipeline routing metadata is never altered by an adapter

**Argument:** An adapter cannot change the `task_header` or `compliance_envelope` fields of the IR. These fields are carried unchanged from `ingress` input to `egress` output on every hop.

**Evidence:**

- Two `MUST`-level validation rules enforce this invariant:
    - `TASK_HEADER_CARRIED` — the `task_header` in the `egress()` return value must be identical to the original
    - `COMPLIANCE_CARRIED` — the `compliance_envelope` in the `egress()` return value must be identical to the original
- The recommended `original_ir.clone()` pattern carries both fields automatically; adapters that reconstruct these fields from scratch will fail both rules.
- Both rules are exercised against all 20 standard fixtures during full validation.
- See: [AdapterValidator reference](reference/validator.md) → `TASK_HEADER_CARRIED`, `COMPLIANCE_CARRIED`.

---

## Claim 4 — The SDK enforces its own correctness

**Argument:** The SDK's enforcement mechanisms are themselves well-tested. A bug in the validator that caused it to pass a non-compliant adapter would undermine all three claims above.

**Evidence:**

- The project maintains ≥ 80% statement coverage across `src/synapse_sdk/` (verified by `pytest --cov` in CI; coverage report is an artifact of every CI run).
- The validator is tested against a set of known-bad adapters — one per rule — that must produce the expected `MUST` failure. These are regression tests: if a rule is accidentally disabled, a known-bad adapter will pass validation and the corresponding test will fail CI.
- Pydantic model validation ensures that malformed IR objects are rejected at construction time, before they can reach any adapter. This is a structural control, not a runtime check.
- Dependency integrity is maintained via `uv.lock` (pinned hashes) and Dependabot (automated CVE alerting).
- See: [Security Requirements](security.md) → Controls 2–5; [AdapterValidator reference](reference/validator.md) → Result types.

---

## Residual Risk

The assurance case covers adapters published through the SDK's standard validation path. It does not cover:

- Adapters that bypass `AdapterValidator` entirely and are loaded directly by an orchestrator that does not call `synapse-validate`
- Vulnerabilities in the model inference code that runs *between* `ingress` and `egress` (outside the SDK boundary)
- Supply-chain attacks on PyPI packages that ship as adapter dependencies

These residual risks are documented in [SECURITY.md](https://github.com/synapse-ir/adapter-sdk/blob/main/SECURITY.md) under the SYNAPSE-specific security model.
