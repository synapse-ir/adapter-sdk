"""Tests for G-S02 — Partial Pipeline Failure (FailurePolicy + PartialCompletionResponse)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from synapse_sdk.types import (
    CanonicalIR,
    Domain,
    FailedStage,
    FailurePolicy,
    PartialCompletionResponse,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_header(failure_policy: FailurePolicy | None = None) -> TaskHeader:
    kwargs: dict = {
        "task_type": TaskType.extract,
        "domain": Domain.legal,
        "priority": 2,
        "latency_budget_ms": 500,
    }
    if failure_policy is not None:
        kwargs["failure_policy"] = failure_policy
    return TaskHeader(**kwargs)


def _make_ir(failure_policy: FailurePolicy | None = None) -> CanonicalIR:
    return CanonicalIR(
        ir_version="1.0.0",
        message_id="00000000-0000-4000-8000-000000000001",
        task_header=_make_header(failure_policy),
        payload=Payload(modality="text", content="test"),
    )


def _make_prov(model_id: str = "model-a") -> ProvenanceEntry:
    return ProvenanceEntry(
        model_id=model_id,
        adapter_version="1.0.0",
        confidence=0.85,
        latency_ms=120,
        timestamp_unix=1_700_000_000,
    )


def _make_payload() -> Payload:
    return Payload(modality="text", content="partial result")


# ---------------------------------------------------------------------------
# FailurePolicy enum
# ---------------------------------------------------------------------------

class TestFailurePolicyEnum:
    def test_values(self):
        assert FailurePolicy.abort    == "abort"
        assert FailurePolicy.partial  == "partial"
        assert FailurePolicy.fallback == "fallback"

    def test_from_string(self):
        assert FailurePolicy("abort")    is FailurePolicy.abort
        assert FailurePolicy("partial")  is FailurePolicy.partial
        assert FailurePolicy("fallback") is FailurePolicy.fallback

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            FailurePolicy("skip")


# ---------------------------------------------------------------------------
# TaskHeader.failure_policy field
# ---------------------------------------------------------------------------

class TestTaskHeaderFailurePolicy:
    def test_default_is_abort(self):
        th = _make_header()
        assert th.failure_policy == FailurePolicy.abort

    def test_explicit_abort(self):
        th = _make_header(FailurePolicy.abort)
        assert th.failure_policy == FailurePolicy.abort

    def test_explicit_partial(self):
        th = _make_header(FailurePolicy.partial)
        assert th.failure_policy == FailurePolicy.partial

    def test_explicit_fallback(self):
        th = _make_header(FailurePolicy.fallback)
        assert th.failure_policy == FailurePolicy.fallback

    def test_from_string_value(self):
        th = TaskHeader(
            task_type=TaskType.generate,
            domain=Domain.general,
            priority=1,
            latency_budget_ms=0,
            failure_policy="partial",
        )
        assert th.failure_policy == FailurePolicy.partial

    def test_invalid_failure_policy_rejected(self):
        with pytest.raises((ValidationError, ValueError)):
            TaskHeader(
                task_type=TaskType.generate,
                domain=Domain.general,
                priority=1,
                latency_budget_ms=0,
                failure_policy="unknown",
            )

    def test_round_trip_json_abort(self):
        ir = _make_ir(FailurePolicy.abort)
        ir2 = CanonicalIR.from_json(ir.to_json())
        assert ir2.task_header.failure_policy == FailurePolicy.abort

    def test_round_trip_json_partial(self):
        ir = _make_ir(FailurePolicy.partial)
        ir2 = CanonicalIR.from_json(ir.to_json())
        assert ir2.task_header.failure_policy == FailurePolicy.partial

    def test_round_trip_json_fallback(self):
        ir = _make_ir(FailurePolicy.fallback)
        ir2 = CanonicalIR.from_json(ir.to_json())
        assert ir2.task_header.failure_policy == FailurePolicy.fallback

    def test_serialised_json_contains_failure_policy(self):
        ir = _make_ir(FailurePolicy.partial)
        data = json.loads(ir.to_json())
        assert data["task_header"]["failure_policy"] == "partial"

    def test_backward_compatible_old_ir_defaults_abort(self):
        """IRs serialised before failure_policy existed round-trip correctly."""
        ir = _make_ir()
        raw = json.loads(ir.to_json())
        # Simulate an old serialised IR with no failure_policy key
        del raw["task_header"]["failure_policy"]
        ir2 = CanonicalIR.model_validate(raw)
        assert ir2.task_header.failure_policy == FailurePolicy.abort


# ---------------------------------------------------------------------------
# FailedStage schema
# ---------------------------------------------------------------------------

class TestFailedStage:
    def test_minimal_construction(self):
        fs = FailedStage(model_id="clause-ext-v1.4", error="MODEL_TIMEOUT")
        assert fs.model_id == "clause-ext-v1.4"
        assert fs.error == "MODEL_TIMEOUT"
        assert fs.detail is None
        assert fs.stage_index is None

    def test_full_construction(self):
        fs = FailedStage(
            model_id="clause-ext-v1.4",
            error="MODEL_TIMEOUT",
            detail="model did not respond within latency_budget_ms=180",
            stage_index=2,
        )
        assert fs.detail == "model did not respond within latency_budget_ms=180"
        assert fs.stage_index == 2

    def test_stage_index_must_be_non_negative(self):
        with pytest.raises((ValidationError, ValueError)):
            FailedStage(model_id="m", error="E", stage_index=-1)

    def test_null_byte_in_model_id_rejected(self):
        with pytest.raises(Exception):
            FailedStage(model_id="bad\x00model", error="E")

    def test_null_byte_in_error_rejected(self):
        with pytest.raises(Exception):
            FailedStage(model_id="m", error="ERR\x00OR")

    def test_extra_fields_forbidden(self):
        with pytest.raises((ValidationError, ValueError)):
            FailedStage(model_id="m", error="E", unexpected="x")

    def test_json_round_trip(self):
        fs = FailedStage(model_id="m", error="TIMEOUT", detail="too slow", stage_index=1)
        data = fs.model_dump_json()
        fs2 = FailedStage.model_validate_json(data)
        assert fs2.model_id == "m"
        assert fs2.stage_index == 1


# ---------------------------------------------------------------------------
# PartialCompletionResponse schema
# ---------------------------------------------------------------------------

class TestPartialCompletionResponse:
    def test_minimal_construction(self):
        resp = PartialCompletionResponse(
            completed_stages=["ner-legal-v2.1"],
            failed_stages=[FailedStage(model_id="clause-ext-v1.4", error="MODEL_TIMEOUT")],
            payload=_make_payload(),
        )
        assert resp.partial_completion is True
        assert resp.completed_stages == ["ner-legal-v2.1"]
        assert len(resp.failed_stages) == 1
        assert resp.provenance == []

    def test_partial_completion_always_true(self):
        resp = PartialCompletionResponse(
            completed_stages=[],
            failed_stages=[FailedStage(model_id="m", error="E")],
            payload=_make_payload(),
        )
        assert resp.partial_completion is True

    def test_with_provenance(self):
        resp = PartialCompletionResponse(
            completed_stages=["ner-legal-v2.1"],
            failed_stages=[FailedStage(model_id="f", error="E")],
            payload=_make_payload(),
            provenance=[_make_prov("ner-legal-v2.1")],
        )
        assert len(resp.provenance) == 1
        assert resp.provenance[0].model_id == "ner-legal-v2.1"

    def test_multiple_failed_stages(self):
        resp = PartialCompletionResponse(
            completed_stages=[],
            failed_stages=[
                FailedStage(model_id="a", error="TIMEOUT", stage_index=0),
                FailedStage(model_id="b", error="OOM", stage_index=1),
            ],
            payload=_make_payload(),
        )
        assert len(resp.failed_stages) == 2
        assert resp.failed_stages[0].stage_index == 0
        assert resp.failed_stages[1].stage_index == 1

    def test_json_round_trip(self):
        resp = PartialCompletionResponse(
            completed_stages=["s1"],
            failed_stages=[
                FailedStage(model_id="f1", error="TIMEOUT", detail="slow", stage_index=2)
            ],
            payload=Payload(modality="structured", data={"result": "partial"}),
            provenance=[_make_prov("s1")],
        )
        data = resp.model_dump_json()
        resp2 = PartialCompletionResponse.model_validate_json(data)
        assert resp2.completed_stages == ["s1"]
        assert resp2.failed_stages[0].model_id == "f1"
        assert resp2.failed_stages[0].stage_index == 2

    def test_dict_matches_spec_shape(self):
        """Serialised shape matches the §9 G-S02 example."""
        resp = PartialCompletionResponse(
            completed_stages=["ner-legal-v2.1"],
            failed_stages=[
                FailedStage(
                    model_id="clause-ext-v1.4",
                    error="MODEL_TIMEOUT",
                    detail="model did not respond within latency_budget_ms=180",
                    stage_index=2,
                )
            ],
            payload=_make_payload(),
            provenance=[_make_prov("ner-legal-v2.1")],
        )
        d = resp.model_dump()
        assert d["partial_completion"] is True
        assert d["completed_stages"] == ["ner-legal-v2.1"]
        assert d["failed_stages"][0]["error"] == "MODEL_TIMEOUT"
        assert d["failed_stages"][0]["stage_index"] == 2
        assert len(d["provenance"]) == 1

    def test_extra_fields_forbidden(self):
        with pytest.raises((ValidationError, ValueError)):
            PartialCompletionResponse(
                completed_stages=[],
                failed_stages=[],
                payload=_make_payload(),
                unexpected_field="x",
            )
