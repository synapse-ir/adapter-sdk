"""Tests for AdapterBase (base.py)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest

from synapse_sdk.base import AdapterBase, AdapterConfigurationError
from synapse_sdk.types import (
    CanonicalIR,
    Domain,
    Payload,
    TaskHeader,
    TaskType,
)

# ---------------------------------------------------------------------------
# Minimal concrete adapter for testing AdapterBase directly
# ---------------------------------------------------------------------------

class _SimpleAdapter(AdapterBase):
    MODEL_ID = "test-model-v1.0"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        return {"text": ir.payload.content}

    def egress(
        self,
        model_output: dict[str, Any],
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        updated = original_ir.clone()
        updated.provenance.append(
            self.build_provenance(confidence=0.9, latency_ms=latency_ms)
        )
        return updated


def _make_ir() -> CanonicalIR:
    return CanonicalIR(
        ir_version="1.0.0",
        message_id=str(uuid.uuid4()),
        task_header=TaskHeader(
            task_type=TaskType.extract,
            domain=Domain.legal,
            priority=1,
            latency_budget_ms=100,
        ),
        payload=Payload(modality="text", content="Hello world."),
    )


# ---------------------------------------------------------------------------
# Abstract enforcement
# ---------------------------------------------------------------------------

def test_cannot_instantiate_abstract():
    class _Incomplete(AdapterBase):
        MODEL_ID = "x"
        ADAPTER_VERSION = "1.0.0"

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


def test_concrete_adapter_instantiates():
    adapter = _SimpleAdapter()
    assert adapter.MODEL_ID == "test-model-v1.0"
    assert adapter.ADAPTER_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# ingress
# ---------------------------------------------------------------------------

def test_ingress_returns_dict():
    adapter = _SimpleAdapter()
    result = adapter.ingress(_make_ir())
    assert isinstance(result, dict)
    assert result["text"] == "Hello world."


# ---------------------------------------------------------------------------
# egress
# ---------------------------------------------------------------------------

def test_egress_returns_canonical_ir():
    adapter = _SimpleAdapter()
    out = adapter.egress({"result": "ok"}, _make_ir(), latency_ms=50)
    assert isinstance(out, CanonicalIR)


def test_egress_appends_provenance():
    adapter = _SimpleAdapter()
    ir = _make_ir()
    assert len(ir.provenance) == 0
    out = adapter.egress({}, ir, latency_ms=30)
    assert len(out.provenance) == 1


def test_egress_carries_task_header():
    adapter = _SimpleAdapter()
    ir = _make_ir()
    out = adapter.egress({}, ir, latency_ms=10)
    assert out.task_header.model_dump() == ir.task_header.model_dump()


def test_egress_carries_compliance_envelope():
    adapter = _SimpleAdapter()
    ir = _make_ir()
    out = adapter.egress({}, ir, latency_ms=10)
    assert out.compliance_envelope.model_dump() == ir.compliance_envelope.model_dump()


# ---------------------------------------------------------------------------
# build_provenance — happy path
# ---------------------------------------------------------------------------

def test_build_provenance_fills_model_id():
    adapter = _SimpleAdapter()
    entry = adapter.build_provenance(confidence=0.8, latency_ms=100)
    assert entry.model_id == "test-model-v1.0"
    assert entry.adapter_version == "1.0.0"


def test_build_provenance_boundary_confidence_zero():
    adapter = _SimpleAdapter()
    entry = adapter.build_provenance(confidence=0.0, latency_ms=1)
    assert entry.confidence == 0.0


def test_build_provenance_boundary_confidence_one():
    adapter = _SimpleAdapter()
    entry = adapter.build_provenance(confidence=1.0, latency_ms=1)
    assert entry.confidence == 1.0


def test_build_provenance_optional_fields():
    adapter = _SimpleAdapter()
    ts = int(time.time())
    entry = adapter.build_provenance(
        confidence=0.5,
        latency_ms=200,
        cost_usd=0.001,
        token_count=128,
        warnings=["truncated"],
        timestamp_unix=ts,
    )
    assert entry.cost_usd == 0.001
    assert entry.token_count == 128
    assert entry.warnings == ["truncated"]
    assert entry.timestamp_unix == ts


def test_build_provenance_auto_timestamp():
    before = int(time.time())
    entry = _SimpleAdapter().build_provenance(confidence=0.5, latency_ms=10)
    after = int(time.time())
    assert before <= entry.timestamp_unix <= after


# ---------------------------------------------------------------------------
# build_provenance — G-C06 error envelopes
# ---------------------------------------------------------------------------

def test_rejects_confidence_above_1():
    with pytest.raises(AdapterConfigurationError) as exc_info:
        _SimpleAdapter().build_provenance(confidence=1.1, latency_ms=10)
    env = exc_info.value.envelope
    assert env["error"] == "ADAPTER_CONFIGURATION_ERROR"
    assert env["field"] == "confidence"
    assert env["received"] == 1.1


def test_rejects_negative_confidence():
    with pytest.raises(AdapterConfigurationError) as exc_info:
        _SimpleAdapter().build_provenance(confidence=-0.1, latency_ms=10)
    assert exc_info.value.envelope["field"] == "confidence"


def test_rejects_negative_latency():
    with pytest.raises(AdapterConfigurationError) as exc_info:
        _SimpleAdapter().build_provenance(confidence=0.5, latency_ms=-1)
    env = exc_info.value.envelope
    assert env["field"] == "latency_ms"
    assert env["received"] == -1


def test_rejects_negative_cost():
    with pytest.raises(AdapterConfigurationError) as exc_info:
        _SimpleAdapter().build_provenance(confidence=0.5, latency_ms=10, cost_usd=-0.01)
    assert exc_info.value.envelope["field"] == "cost_usd"


def test_error_envelope_is_json_serialisable():
    import json
    with pytest.raises(AdapterConfigurationError) as exc_info:
        _SimpleAdapter().build_provenance(confidence=99.0, latency_ms=0)
    parsed = json.loads(str(exc_info.value))
    assert "error" in parsed
    assert "recommendation" in parsed
