"""Standard fixture library — §9 G-S06.

All 20 representative IR payloads used to validate adapter implementations.
Every adapter author runs against the same fixtures to ensure cross-adapter
consistency and to catch edge cases before production.

Usage::

    from synapse_sdk.testing.fixtures import LEGAL_EXTRACT_BASIC, ALL_FIXTURES
    from synapse_sdk.validator import AdapterValidator

    result = AdapterValidator(my_adapter, fixtures=ALL_FIXTURES).run()
"""

from __future__ import annotations

import base64

from synapse_sdk.types import (
    CanonicalIR,
    ComplianceEnvelope,
    Domain,
    FailurePolicy,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
    TraceContext,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _prov(model_id: str, index: int) -> ProvenanceEntry:
    return ProvenanceEntry(
        model_id=model_id,
        adapter_version="1.0.0",
        confidence=0.90,
        latency_ms=120,
        timestamp_unix=1_700_000_000 + index,
    )


_PRIOR_MODEL = "synapse/prior-model"

# Deterministic UUIDs — one per fixture, in slot order
_IDS = [
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002",
    "00000000-0000-4000-8000-000000000003",
    "00000000-0000-4000-8000-000000000004",
    "00000000-0000-4000-8000-000000000005",
    "00000000-0000-4000-8000-000000000006",
    "00000000-0000-4000-8000-000000000007",
    "00000000-0000-4000-8000-000000000008",
    "00000000-0000-4000-8000-000000000009",
    "00000000-0000-4000-8000-000000000010",
    "00000000-0000-4000-8000-000000000011",
    "00000000-0000-4000-8000-000000000012",
    "00000000-0000-4000-8000-000000000013",
    "00000000-0000-4000-8000-000000000014",
    "00000000-0000-4000-8000-000000000015",
    "00000000-0000-4000-8000-000000000016",
    "00000000-0000-4000-8000-000000000017",
    "00000000-0000-4000-8000-000000000018",
    "00000000-0000-4000-8000-000000000019",
    "00000000-0000-4000-8000-000000000020",
]


# ---------------------------------------------------------------------------
# 1. LEGAL_EXTRACT_BASIC
# ---------------------------------------------------------------------------

LEGAL_EXTRACT_BASIC = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[0],
    task_header=TaskHeader(
        task_type=TaskType.extract,
        domain=Domain.legal,
        priority=2,
        latency_budget_ms=500,
    ),
    payload=Payload(
        modality="text",
        content=(
            "The court held that the defendant was liable for breach of contract "
            "under §2-314 of the UCC, as the goods delivered did not conform to "
            "the implied warranty of merchantability."
        ),
    ),
)
"""Baseline legal extraction. No optional fields populated.

Edge case: ensures adapters produce valid output from the minimum required
IR structure. All legal adapters must pass this before any other fixture.
"""


# ---------------------------------------------------------------------------
# 2. LEGAL_EXTRACT_PII
# ---------------------------------------------------------------------------

LEGAL_EXTRACT_PII = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[1],
    task_header=TaskHeader(
        task_type=TaskType.extract,
        domain=Domain.legal,
        priority=1,
        latency_budget_ms=500,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Plaintiff John Smith (SSN: 123-45-6789) filed suit against Acme Corp "
            "on 14 March 2024 alleging wrongful termination."
        ),
    ),
    compliance_envelope=ComplianceEnvelope(
        pii_present=True,
        required_tags=["gdpr", "ccpa"],
        retention_policy="90d",
    ),
)
"""Legal extraction with pii_present=True.

Edge case: adapters must propagate the compliance_envelope unchanged through
egress(), including pii_present=True. Tests that adapters do not strip or
modify PII-flagged envelopes.
"""


# ---------------------------------------------------------------------------
# 3. MEDICAL_CLASSIFY_HIPAA
# ---------------------------------------------------------------------------

MEDICAL_CLASSIFY_HIPAA = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[2],
    task_header=TaskHeader(
        task_type=TaskType.classify,
        domain=Domain.medical,
        priority=1,
        latency_budget_ms=300,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Patient presents with acute onset chest pain radiating to the left arm, "
            "diaphoresis, and shortness of breath. Troponin I elevated at 2.4 ng/mL. "
            "Suspected STEMI — cardiology consult ordered."
        ),
    ),
    compliance_envelope=ComplianceEnvelope(
        required_tags=["hipaa"],
        pii_present=True,
        data_residency=["us-east-1"],
    ),
)
"""Medical classification requiring hipaa compliance tag.

Edge case: routing must filter to HIPAA-compliant models only. Adapters must
carry the hipaa tag and data_residency constraint through egress unchanged.
"""


# ---------------------------------------------------------------------------
# 4. FINANCE_GENERATE_SOX
# ---------------------------------------------------------------------------

FINANCE_GENERATE_SOX = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[3],
    task_header=TaskHeader(
        task_type=TaskType.generate,
        domain=Domain.finance,
        priority=1,
        latency_budget_ms=2000,
        cost_ceiling=0.05,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Summarize the material weaknesses identified in the internal controls "
            "review for fiscal year 2023, referencing PCAOB AS 2201 standards."
        ),
    ),
    compliance_envelope=ComplianceEnvelope(
        required_tags=["sox", "pcaob", "audit-trail"],
        pii_present=False,
        retention_policy="7y",
        purpose_limitation="financial-reporting",
    ),
)
"""Financial generation with multi-tag SOX compliance.

Edge case: tests that adapters handle multi-tag required_tags lists and that
cost_ceiling is preserved in task_header through the full adapter cycle.
"""


# ---------------------------------------------------------------------------
# 5. GENERAL_EMBED_LARGE
# ---------------------------------------------------------------------------

# ~1.07 MB of text — triggers the 1 MB soft-limit warning in payload validation
_LARGE_CONTENT = "Embedding target document paragraph. " * 30_500

GENERAL_EMBED_LARGE = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[4],
    task_header=TaskHeader(
        task_type=TaskType.embed,
        domain=Domain.general,
        priority=3,
        latency_budget_ms=5000,
    ),
    payload=Payload(
        modality="text",
        content=_LARGE_CONTENT,
        language="en",
    ),
)
"""Embedding request with content near (and slightly over) the 1 MB soft limit.

Edge case: validates that adapters handle large text payloads without
truncation or error. The SDK logs a soft-limit warning on construction;
the adapter must still process this IR and produce valid output.
"""


# ---------------------------------------------------------------------------
# 6. MULTILINGUAL_TRANSLATE
# ---------------------------------------------------------------------------

MULTILINGUAL_TRANSLATE = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[5],
    task_header=TaskHeader(
        task_type=TaskType.translate,
        domain=Domain.multilingual,
        priority=2,
        latency_budget_ms=1500,
    ),
    payload=Payload(
        modality="text",
        content="The agreement shall be governed by the laws of the State of New York.",
        language="en-US",
    ),
)
"""Translation task with BCP-47 language tag on the source content.

Edge case: adapters must read and preserve the payload.language field.
Tests that language-aware adapters correctly identify source language
and do not overwrite it in egress.
"""


# ---------------------------------------------------------------------------
# 7. RANK_WITH_PRIOR_PROVENANCE
# ---------------------------------------------------------------------------

RANK_WITH_PRIOR_PROVENANCE = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[6],
    task_header=TaskHeader(
        task_type=TaskType.rank,
        domain=Domain.general,
        priority=2,
        latency_budget_ms=800,
    ),
    payload=Payload(
        modality="structured",
        data={
            "query": "best practices for secure code review",
            "candidates": [
                "Static analysis tools are the first line of defence.",
                "Manual peer review catches logic errors that tools miss.",
                "Automated tests provide regression coverage.",
            ],
        },
    ),
    provenance=[
        _prov(_PRIOR_MODEL, i) for i in range(5)
    ],
)
"""Ranking task with 5 existing provenance entries from upstream hops.

Edge case: adapters must append exactly one new entry (not replace the five
existing ones). Tests provenance immutability and correct append semantics
when the chain is already non-empty.
"""


# ---------------------------------------------------------------------------
# 8. ZERO_LATENCY_BUDGET
# ---------------------------------------------------------------------------

ZERO_LATENCY_BUDGET = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[7],
    task_header=TaskHeader(
        task_type=TaskType.classify,
        domain=Domain.general,
        priority=3,
        latency_budget_ms=0,
    ),
    payload=Payload(
        modality="text",
        content="Classify the sentiment of this customer feedback.",
    ),
)
"""latency_budget_ms=0 — no latency constraint (any model is acceptable).

Edge case: routing and adapters must treat 0 as 'unconstrained', not as
'must complete in 0 ms'. Adapters that filter on latency_budget_ms must
handle the zero value without rejecting valid IRs.
"""


# ---------------------------------------------------------------------------
# 9. TIGHT_LATENCY_BUDGET
# ---------------------------------------------------------------------------

TIGHT_LATENCY_BUDGET = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[8],
    task_header=TaskHeader(
        task_type=TaskType.classify,
        domain=Domain.general,
        priority=1,
        latency_budget_ms=10,
    ),
    payload=Payload(
        modality="text",
        content="Urgent: classify this alert as critical or non-critical.",
    ),
)
"""latency_budget_ms=10 — extremely tight budget.

Edge case: tests that adapters do not crash or produce invalid IR when given
a budget that most models cannot meet. The adapter itself must still return
a valid IR; the routing layer is responsible for filtering candidates.
"""


# ---------------------------------------------------------------------------
# 10. MAX_PROVENANCE_CHAIN
# ---------------------------------------------------------------------------

MAX_PROVENANCE_CHAIN = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[9],
    task_header=TaskHeader(
        task_type=TaskType.summarize,
        domain=Domain.general,
        priority=2,
        latency_budget_ms=2000,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Summarize the key findings from the multi-stage pipeline that "
            "processed this document across 20 model hops."
        ),
    ),
    provenance=[
        _prov(_PRIOR_MODEL, i) for i in range(20)
    ],
)
"""IR with 20 provenance entries — at the soft limit boundary.

Edge case: tests provenance chain handling at scale. Adapters must append
one more entry (bringing total to 21) without failing. The SDK logs a
warning at >20 entries; the adapter must still produce valid output.
"""


# ---------------------------------------------------------------------------
# 11. EMPTY_COMPLIANCE
# ---------------------------------------------------------------------------

EMPTY_COMPLIANCE = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[10],
    task_header=TaskHeader(
        task_type=TaskType.generate,
        domain=Domain.general,
        priority=3,
        latency_budget_ms=1000,
    ),
    payload=Payload(
        modality="text",
        content="Generate a short product description for a new coffee maker.",
    ),
    compliance_envelope=ComplianceEnvelope(),
)
"""Empty compliance_envelope — no constraints of any kind.

Edge case: adapters must handle a fully-empty envelope without setting
default constraints or raising. Tests that adapters do not assume any
compliance fields are populated.
"""


# ---------------------------------------------------------------------------
# 12. FULL_COMPLIANCE
# ---------------------------------------------------------------------------

FULL_COMPLIANCE = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[11],
    task_header=TaskHeader(
        task_type=TaskType.generate,
        domain=Domain.legal,
        priority=1,
        latency_budget_ms=3000,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Draft a data processing agreement clause covering GDPR Article 28 "
            "controller-processor obligations."
        ),
    ),
    compliance_envelope=ComplianceEnvelope(
        required_tags=["gdpr", "ccpa", "hipaa", "sox", "pcaob", "pci-dss", "audit-trail"],
        pii_present=True,
        data_residency=["eu-west-1", "eu-central-1"],
        retention_policy="7y",
        purpose_limitation="legal-drafting",
    ),
)
"""All known compliance tags set simultaneously.

Edge case: tests complete compliance handling. Adapters must carry all seven
tags, both residency regions, and all string fields through egress unchanged.
"""


# ---------------------------------------------------------------------------
# 13. SESSION_WITH_CONTEXT_REF
# ---------------------------------------------------------------------------

SESSION_WITH_CONTEXT_REF = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[12],
    task_header=TaskHeader(
        task_type=TaskType.generate,
        domain=Domain.general,
        priority=2,
        latency_budget_ms=1000,
        session_id="sess-ctx-ref-test-001",
    ),
    payload=Payload(
        modality="text",
        content="Continue the analysis using the document stored in context.",
        context_ref="ctx://sess-ctx-ref-test-001/document-chunk-7",
    ),
)
"""IR with context_ref set — points to a large payload stored out-of-band.

Edge case: adapters must pass context_ref through to egress without
modification. Tests that adapters do not attempt to dereference or remove
the context_ref field when the payload content alone is small.
"""


# ---------------------------------------------------------------------------
# 14. STRUCTURED_PAYLOAD
# ---------------------------------------------------------------------------

STRUCTURED_PAYLOAD = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[13],
    task_header=TaskHeader(
        task_type=TaskType.extract,
        domain=Domain.general,
        priority=2,
        latency_budget_ms=800,
    ),
    payload=Payload(
        modality="structured",
        data={
            "invoice_id": "INV-2024-00123",
            "vendor": "Acme Supplies Ltd",
            "line_items": [
                {"sku": "WIDGET-A", "qty": 10, "unit_price": 4.99},
                {"sku": "GADGET-B", "qty": 3,  "unit_price": 24.50},
            ],
            "total_usd": 123.40,
            "due_date": "2024-04-30",
        },
        schema_ref="urn:synapse:schema:invoice:v2",
    ),
)
"""payload.modality=structured with a nested data object.

Edge case: tests that adapters correctly handle structured (non-text)
payloads. Adapters must read from payload.data, not payload.content
(which is None for structured modality).
"""


# ---------------------------------------------------------------------------
# 15. BINARY_PAYLOAD
# ---------------------------------------------------------------------------

_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
_PDF_B64 = base64.b64encode(_PDF_BYTES).decode("ascii")

BINARY_PAYLOAD = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[14],
    task_header=TaskHeader(
        task_type=TaskType.extract,
        domain=Domain.legal,
        priority=2,
        latency_budget_ms=2000,
    ),
    payload=Payload(
        modality="binary",
        binary_b64=_PDF_B64,
        mime_type="application/pdf",
        byte_length=len(_PDF_BYTES),
    ),
)
"""payload.modality=binary with base64-encoded PDF content.

Edge case: tests binary modality handling. Adapters that do not support
binary input must still return a valid CanonicalIR (even if they skip
processing) rather than raising. mime_type and byte_length must be carried
through or updated in egress.
"""


# ---------------------------------------------------------------------------
# 16. VALIDATE_TASK
# ---------------------------------------------------------------------------

VALIDATE_TASK = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[15],
    task_header=TaskHeader(
        task_type=TaskType.validate,
        domain=Domain.legal,
        priority=2,
        latency_budget_ms=600,
    ),
    payload=Payload(
        modality="text",
        content=(
            "This contract clause states that the limitation of liability shall "
            "not exceed the total fees paid in the preceding twelve months."
        ),
    ),
)
"""task_type=validate — checks that all registered task types are handled.

Edge case: adapters that only implement a subset of task types must still
return a valid CanonicalIR for task_type=validate. Tests that adapters do
not special-case task types in egress in a way that breaks the contract.
"""


# ---------------------------------------------------------------------------
# 17. SCORE_TASK
# ---------------------------------------------------------------------------

SCORE_TASK = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[16],
    task_header=TaskHeader(
        task_type=TaskType.score,
        domain=Domain.general,
        priority=2,
        latency_budget_ms=400,
        quality_floor=0.9,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Evaluate the following machine translation output for fluency "
            "and adequacy on a scale of 0 to 1."
        ),
    ),
)
"""task_type=score with quality_floor=0.9.

Edge case: tests that adapters handle quality_floor constraints in
task_header. The adapter's confidence in build_provenance() should reflect
the adapter's own quality assessment; quality_floor is a routing hint and
must not be stripped or modified in egress.
"""


# ---------------------------------------------------------------------------
# 18. PARTIAL_FAILURE_POLICY
# ---------------------------------------------------------------------------

PARTIAL_FAILURE_POLICY = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[17],
    task_header=TaskHeader(
        task_type=TaskType.extract,
        domain=Domain.legal,
        priority=2,
        latency_budget_ms=1000,
        failure_policy=FailurePolicy.partial,
    ),
    payload=Payload(
        modality="text",
        content=(
            "Extract all named entities from this document, returning partial "
            "results if some entity types cannot be resolved."
        ),
    ),
)
"""failure_policy=partial in task_header.

Edge case: tests failure policy propagation through the adapter cycle.
Adapters must carry task_header.failure_policy through egress unchanged;
the pipeline runner reads it to decide whether to raise or return a
PartialCompletionResponse when a stage fails.
"""


# ---------------------------------------------------------------------------
# 19. TRACE_CONTEXT_SET
# ---------------------------------------------------------------------------

# W3C traceparent: version=00, trace-id (32 hex), parent-id (16 hex), flags=01
_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

TRACE_CONTEXT_SET = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[18],
    task_header=TaskHeader(
        task_type=TaskType.extract,
        domain=Domain.legal,
        priority=2,
        latency_budget_ms=500,
        trace_context=TraceContext(traceparent=_TRACEPARENT),
    ),
    payload=Payload(
        modality="text",
        content="Extract clauses for distributed trace context propagation testing.",
    ),
)
"""trace_context.traceparent set — tests W3C trace context propagation.

Edge case: adapters must read task_header.trace_context and propagate the
traceparent into their outbound span so distributed tracing works end-to-end.
Adapters must not strip or overwrite trace_context in egress.
"""


# ---------------------------------------------------------------------------
# 20. MINIMAL_VALID_IR
# ---------------------------------------------------------------------------

MINIMAL_VALID_IR = CanonicalIR(
    ir_version="1.0.0",
    message_id=_IDS[19],
    task_header=TaskHeader(
        task_type=TaskType.classify,
        domain=Domain.general,
        priority=2,
        latency_budget_ms=500,
    ),
    payload=Payload(
        modality="text",
        content="Hello.",
    ),
)
"""Absolute minimum valid IR — only required fields, no optionals.

Edge case: forward-compatibility baseline. Any adapter that fails this
fixture cannot handle the simplest possible IR and has a fundamental
implementation error. Also used to verify that future schema additions
do not break existing minimal IRs.
"""


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

ALL_FIXTURES: list[CanonicalIR] = [
    LEGAL_EXTRACT_BASIC,
    LEGAL_EXTRACT_PII,
    MEDICAL_CLASSIFY_HIPAA,
    FINANCE_GENERATE_SOX,
    GENERAL_EMBED_LARGE,
    MULTILINGUAL_TRANSLATE,
    RANK_WITH_PRIOR_PROVENANCE,
    ZERO_LATENCY_BUDGET,
    TIGHT_LATENCY_BUDGET,
    MAX_PROVENANCE_CHAIN,
    EMPTY_COMPLIANCE,
    FULL_COMPLIANCE,
    SESSION_WITH_CONTEXT_REF,
    STRUCTURED_PAYLOAD,
    BINARY_PAYLOAD,
    VALIDATE_TASK,
    SCORE_TASK,
    PARTIAL_FAILURE_POLICY,
    TRACE_CONTEXT_SET,
    MINIMAL_VALID_IR,
]

FIXTURE_NAMES: list[str] = [
    "LEGAL_EXTRACT_BASIC",
    "LEGAL_EXTRACT_PII",
    "MEDICAL_CLASSIFY_HIPAA",
    "FINANCE_GENERATE_SOX",
    "GENERAL_EMBED_LARGE",
    "MULTILINGUAL_TRANSLATE",
    "RANK_WITH_PRIOR_PROVENANCE",
    "ZERO_LATENCY_BUDGET",
    "TIGHT_LATENCY_BUDGET",
    "MAX_PROVENANCE_CHAIN",
    "EMPTY_COMPLIANCE",
    "FULL_COMPLIANCE",
    "SESSION_WITH_CONTEXT_REF",
    "STRUCTURED_PAYLOAD",
    "BINARY_PAYLOAD",
    "VALIDATE_TASK",
    "SCORE_TASK",
    "PARTIAL_FAILURE_POLICY",
    "TRACE_CONTEXT_SET",
    "MINIMAL_VALID_IR",
]

__all__ = [
    "ALL_FIXTURES",
    "FIXTURE_NAMES",
    "LEGAL_EXTRACT_BASIC",
    "LEGAL_EXTRACT_PII",
    "MEDICAL_CLASSIFY_HIPAA",
    "FINANCE_GENERATE_SOX",
    "GENERAL_EMBED_LARGE",
    "MULTILINGUAL_TRANSLATE",
    "RANK_WITH_PRIOR_PROVENANCE",
    "ZERO_LATENCY_BUDGET",
    "TIGHT_LATENCY_BUDGET",
    "MAX_PROVENANCE_CHAIN",
    "EMPTY_COMPLIANCE",
    "FULL_COMPLIANCE",
    "SESSION_WITH_CONTEXT_REF",
    "STRUCTURED_PAYLOAD",
    "BINARY_PAYLOAD",
    "VALIDATE_TASK",
    "SCORE_TASK",
    "PARTIAL_FAILURE_POLICY",
    "TRACE_CONTEXT_SET",
    "MINIMAL_VALID_IR",
]
