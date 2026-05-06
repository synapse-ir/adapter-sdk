"""Tests for NERBertAdapter — covers unit behaviour and full AdapterValidator suite."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from adapters.ner_bert_adapter import NERBertAdapter
from synapse_sdk.testing.fixtures import ALL_FIXTURES
from synapse_sdk.types import (
    CanonicalIR,
    ComplianceEnvelope,
    Domain,
    Payload,
    TaskHeader,
    TaskType,
)
from synapse_sdk.validator import AdapterValidator


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_ir(
    content: str | None = "Acme Corp signed an agreement with John Smith.",
    modality: str = "text",
    quality_floor: float | None = None,
    compliance: ComplianceEnvelope | None = None,
) -> CanonicalIR:
    payload_kwargs: dict[str, Any] = {"modality": modality}
    if modality == "text":
        payload_kwargs["content"] = content
    elif modality == "structured":
        payload_kwargs["data"] = {"key": "value"}
    elif modality == "binary":
        import base64
        payload_kwargs["binary_b64"] = base64.b64encode(b"data").decode()
        payload_kwargs["mime_type"] = "application/octet-stream"

    return CanonicalIR(
        ir_version="1.0.0",
        message_id=str(uuid.uuid4()),
        task_header=TaskHeader(
            task_type=TaskType.extract,
            domain=Domain.general,
            priority=2,
            latency_budget_ms=500,
            quality_floor=quality_floor,
        ),
        payload=Payload(**payload_kwargs),
        compliance_envelope=compliance or ComplianceEnvelope(),
    )


# Mock model output matching dslim/bert-base-NER pipeline format
_ORG_OUTPUT: list[dict[str, Any]] = [
    {"entity": "B-ORG", "score": 0.9996282, "index": 1, "word": "Acme", "start": 0, "end": 4},
    {"entity": "I-ORG", "score": 0.9994332, "index": 2, "word": "Corp", "start": 5, "end": 9},
]

_PER_OUTPUT: list[dict[str, Any]] = [
    {"entity": "B-PER", "score": 0.9990, "index": 4, "word": "John", "start": 11, "end": 15},
    {"entity": "I-PER", "score": 0.9985, "index": 5, "word": "Smith", "start": 16, "end": 21},
]

_MIXED_OUTPUT: list[dict[str, Any]] = _ORG_OUTPUT + _PER_OUTPUT

_FULL_OUTPUT: list[dict[str, Any]] = [
    {"entity": "B-ORG",  "score": 0.9996282,  "index": 11, "word": "A",    "start": 43, "end": 44},
    {"entity": "I-ORG",  "score": 0.94490504,  "index": 12, "word": "##c",  "start": 44, "end": 45},
    {"entity": "I-ORG",  "score": 0.9989988,   "index": 13, "word": "##me", "start": 45, "end": 47},
    {"entity": "I-ORG",  "score": 0.9994332,   "index": 14, "word": "Corp", "start": 48, "end": 52},
]


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_model_id():
    assert NERBertAdapter().MODEL_ID == "dslim/bert-base-NER"


def test_adapter_version_semver():
    ver = NERBertAdapter().ADAPTER_VERSION
    parts = ver.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# ---------------------------------------------------------------------------
# ingress
# ---------------------------------------------------------------------------

def test_ingress_returns_dict():
    result = NERBertAdapter().ingress(_make_ir())
    assert isinstance(result, dict)


def test_ingress_text_content():
    ir = _make_ir(content="Hello world.")
    result = NERBertAdapter().ingress(ir)
    assert result["text"] == "Hello world."


def test_ingress_none_content_becomes_empty_string():
    ir = _make_ir(modality="structured")
    result = NERBertAdapter().ingress(ir)
    assert result["text"] == ""


def test_ingress_quality_floor_included():
    ir = _make_ir(quality_floor=0.85)
    result = NERBertAdapter().ingress(ir)
    assert result["threshold"] == pytest.approx(0.85)


def test_ingress_no_quality_floor_omits_threshold():
    result = NERBertAdapter().ingress(_make_ir(quality_floor=None))
    assert "threshold" not in result


# ---------------------------------------------------------------------------
# egress — return type and structure
# ---------------------------------------------------------------------------

def test_egress_returns_canonical_ir():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=100)
    assert isinstance(out, CanonicalIR)


def test_egress_appends_exactly_one_provenance():
    ir = _make_ir()
    out = NERBertAdapter().egress(_ORG_OUTPUT, ir, latency_ms=100)
    assert len(out.provenance) == len(ir.provenance) + 1


def test_egress_provenance_model_id():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    assert out.provenance[-1].model_id == "dslim/bert-base-NER"


def test_egress_carries_task_header():
    ir = _make_ir()
    out = NERBertAdapter().egress(_ORG_OUTPUT, ir, latency_ms=50)
    assert out.task_header.model_dump() == ir.task_header.model_dump()


# ---------------------------------------------------------------------------
# egress — entity mapping
# ---------------------------------------------------------------------------

def test_egress_maps_entities_to_payload():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    assert out.payload.entities is not None
    assert len(out.payload.entities) == 2


def test_egress_entity_label_from_entity_field():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    labels = [e.label for e in out.payload.entities]
    assert "B-ORG" in labels
    assert "I-ORG" in labels


def test_egress_entity_text_from_word_field():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    texts = [e.text for e in out.payload.entities]
    assert "Acme" in texts
    assert "Corp" in texts


def test_egress_entity_confidence_from_score():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    confs = [e.confidence for e in out.payload.entities]
    assert all(0.0 <= c <= 1.0 for c in confs)


def test_egress_entity_offsets_carried():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    first = out.payload.entities[0]
    assert first.start == 0
    assert first.end == 4


# ---------------------------------------------------------------------------
# egress — confidence aggregation
# ---------------------------------------------------------------------------

def test_egress_confidence_is_mean_of_scores():
    out = NERBertAdapter().egress(_ORG_OUTPUT, _make_ir(), latency_ms=50)
    expected = (0.9996282 + 0.9994332) / 2
    assert out.provenance[-1].confidence == pytest.approx(expected, abs=1e-5)


def test_egress_empty_output_confidence_zero():
    out = NERBertAdapter().egress([], _make_ir(), latency_ms=50)
    assert out.provenance[-1].confidence == 0.0


def test_egress_full_sample_confidence():
    out = NERBertAdapter().egress(_FULL_OUTPUT, _make_ir(), latency_ms=50)
    scores = [item["score"] for item in _FULL_OUTPUT]
    expected = sum(scores) / len(scores)
    assert out.provenance[-1].confidence == pytest.approx(expected, abs=1e-5)


# ---------------------------------------------------------------------------
# egress — G-S04 PII detection
# ---------------------------------------------------------------------------

def test_egress_no_per_entities_pii_unchanged():
    ir = _make_ir(compliance=ComplianceEnvelope(pii_present=None))
    out = NERBertAdapter().egress(_ORG_OUTPUT, ir, latency_ms=50)
    assert out.compliance_envelope.pii_present is None


def test_egress_per_entity_sets_pii_present_true():
    ir = _make_ir(compliance=ComplianceEnvelope(pii_present=None))
    out = NERBertAdapter().egress(_PER_OUTPUT, ir, latency_ms=50)
    assert out.compliance_envelope.pii_present is True


def test_egress_per_entity_in_mixed_output_sets_pii():
    ir = _make_ir(compliance=ComplianceEnvelope())
    out = NERBertAdapter().egress(_MIXED_OUTPUT, ir, latency_ms=50)
    assert out.compliance_envelope.pii_present is True


def test_egress_pii_already_true_remains_true():
    ir = _make_ir(compliance=ComplianceEnvelope(pii_present=True))
    out = NERBertAdapter().egress(_PER_OUTPUT, ir, latency_ms=50)
    assert out.compliance_envelope.pii_present is True


def test_egress_pii_upgrade_preserves_other_compliance_fields():
    compliance = ComplianceEnvelope(
        pii_present=None,
        required_tags=["gdpr"],
        retention_policy="30d",
        data_residency=["eu-west-1"],
        purpose_limitation="legal",
    )
    ir = _make_ir(compliance=compliance)
    out = NERBertAdapter().egress(_PER_OUTPUT, ir, latency_ms=50)
    env = out.compliance_envelope
    assert env.pii_present is True
    assert env.required_tags == ["gdpr"]
    assert env.retention_policy == "30d"
    assert env.data_residency == ["eu-west-1"]
    assert env.purpose_limitation == "legal"


def test_egress_carries_compliance_when_no_pii():
    compliance = ComplianceEnvelope(
        required_tags=["sox"],
        pii_present=False,
        retention_policy="7y",
    )
    ir = _make_ir(compliance=compliance)
    out = NERBertAdapter().egress(_ORG_OUTPUT, ir, latency_ms=50)
    assert out.compliance_envelope.model_dump() == compliance.model_dump()


# ---------------------------------------------------------------------------
# egress — non-list model output (validator dummy format)
# ---------------------------------------------------------------------------

def test_egress_dict_output_produces_empty_entities():
    dummy = {"result": "test", "model_conf": 0.9}
    out = NERBertAdapter().egress(dummy, _make_ir(), latency_ms=42)
    assert isinstance(out, CanonicalIR)
    assert out.payload.entities is None or out.payload.entities == []


def test_egress_dict_output_confidence_zero():
    out = NERBertAdapter().egress({"result": "x"}, _make_ir(), latency_ms=42)
    assert out.provenance[-1].confidence == 0.0


def test_egress_none_output_handled():
    out = NERBertAdapter().egress(None, _make_ir(), latency_ms=42)
    assert isinstance(out, CanonicalIR)


# ---------------------------------------------------------------------------
# egress — content is not mutated (CONTENT_PRESERVED)
# ---------------------------------------------------------------------------

def test_egress_does_not_mutate_content():
    ir = _make_ir(content="Original text.")
    out = NERBertAdapter().egress(_ORG_OUTPUT, ir, latency_ms=50)
    assert out.payload.content == "Original text."


# ---------------------------------------------------------------------------
# np.float32 score compatibility (G-C02: scores from real pipeline)
# ---------------------------------------------------------------------------

def test_egress_handles_numpy_float32_scores():
    try:
        import numpy as np
        np_output = [
            {"entity": "B-ORG", "score": np.float32(0.9996282), "index": 1,
             "word": "Acme", "start": 0, "end": 4},
        ]
        out = NERBertAdapter().egress(np_output, _make_ir(), latency_ms=50)
        assert 0.0 <= out.provenance[-1].confidence <= 1.0
    except ImportError:
        pytest.skip("numpy not installed")


# ---------------------------------------------------------------------------
# AdapterValidator — all 20 standard fixtures (§9 G-S06)
# ---------------------------------------------------------------------------

def test_validator_all_fixtures():
    """NERBertAdapter must pass all 13 MUST rules across all 20 standard fixtures."""
    AdapterValidator(NERBertAdapter(), fixtures=ALL_FIXTURES).assert_valid()


def test_validator_result_has_no_errors():
    result = AdapterValidator(NERBertAdapter(), fixtures=ALL_FIXTURES).run()
    assert result.passed, result.summary()
