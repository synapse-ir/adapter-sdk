# SPDX-FileCopyrightText: 2024 Chris Widmer
# SPDX-License-Identifier: MIT
"""Property-based tests using Hypothesis for dynamic analysis (Gold criterion: dynamic_analysis)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from synapse_sdk.base import AdapterBase, AdapterConfigurationError
from synapse_sdk.types import (
    CanonicalIR,
    Domain,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
)


# ---------------------------------------------------------------------------
# Minimal concrete adapter for property tests
# ---------------------------------------------------------------------------

class _EchoAdapter(AdapterBase):
    MODEL_ID = "test-org/echo-v1"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        return {"content": ir.payload.content}

    def egress(self, model_output: dict[str, Any], original_ir: CanonicalIR, latency_ms: int) -> CanonicalIR:
        updated = original_ir.clone()
        updated.provenance.append(
            self.build_provenance(confidence=0.9, latency_ms=latency_ms)
        )
        return updated


_adapter = _EchoAdapter()


def _make_ir(content: str = "hello") -> CanonicalIR:
    return CanonicalIR(
        ir_version="1.0.0",
        message_id=str(uuid.uuid4()),
        task_header=TaskHeader(
            task_type=TaskType.classify,
            domain=Domain.general,
            priority=1,
            latency_budget_ms=1000,
        ),
        payload=Payload(modality="text", content=content),
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_confidence = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
invalid_confidence = st.one_of(
    st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.001, allow_nan=False, allow_infinity=False),
)
valid_latency = st.integers(min_value=0, max_value=10_000_000)
invalid_latency = st.integers(max_value=-1)
valid_cost = st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)
invalid_cost = st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False)

printable_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=500,
)


# ---------------------------------------------------------------------------
# build_provenance — boundary conditions
# ---------------------------------------------------------------------------

@given(confidence=valid_confidence, latency_ms=valid_latency)
@settings(max_examples=200)
def test_build_provenance_valid(confidence: float, latency_ms: int) -> None:
    prov = _adapter.build_provenance(confidence=confidence, latency_ms=latency_ms)
    assert isinstance(prov, ProvenanceEntry)
    assert prov.confidence == confidence
    assert prov.latency_ms == latency_ms
    assert prov.model_id == "test-org/echo-v1"


@given(confidence=invalid_confidence)
def test_build_provenance_rejects_bad_confidence(confidence: float) -> None:
    with pytest.raises(AdapterConfigurationError):
        _adapter.build_provenance(confidence=confidence, latency_ms=0)


@given(latency_ms=invalid_latency)
def test_build_provenance_rejects_negative_latency(latency_ms: int) -> None:
    with pytest.raises(AdapterConfigurationError):
        _adapter.build_provenance(confidence=0.5, latency_ms=latency_ms)


@given(cost_usd=valid_cost)
@settings(max_examples=100)
def test_build_provenance_valid_cost(cost_usd: float) -> None:
    prov = _adapter.build_provenance(confidence=0.5, latency_ms=0, cost_usd=cost_usd)
    assert prov.cost_usd == cost_usd


@given(cost_usd=invalid_cost)
def test_build_provenance_rejects_negative_cost(cost_usd: float) -> None:
    with pytest.raises(AdapterConfigurationError):
        _adapter.build_provenance(confidence=0.5, latency_ms=0, cost_usd=cost_usd)


# ---------------------------------------------------------------------------
# CanonicalIR construction — valid content strings
# ---------------------------------------------------------------------------

@given(content=printable_text)
@settings(max_examples=200)
def test_canonical_ir_accepts_valid_content(content: str) -> None:
    ir = _make_ir(content)
    assert ir.payload.content == content


# ---------------------------------------------------------------------------
# Null bytes are always rejected (G-C05 injection protection)
# ---------------------------------------------------------------------------

@given(prefix=st.text(min_size=0, max_size=100))
def test_canonical_ir_rejects_null_bytes(prefix: str) -> None:
    with pytest.raises(Exception):
        _make_ir(prefix + "\x00")


# ---------------------------------------------------------------------------
# Round-trip: ingress always returns a dict with content
# ---------------------------------------------------------------------------

@given(content=printable_text)
@settings(max_examples=100)
def test_ingress_always_returns_dict(content: str) -> None:
    ir = _make_ir(content)
    result = _adapter.ingress(ir)
    assert isinstance(result, dict)
    assert result["content"] == content


# ---------------------------------------------------------------------------
# Provenance append: egress always adds exactly one entry
# ---------------------------------------------------------------------------

@given(content=printable_text, latency_ms=valid_latency)
@settings(max_examples=100)
def test_egress_appends_exactly_one_provenance(content: str, latency_ms: int) -> None:
    ir = _make_ir(content)
    before = len(ir.provenance)
    result = _adapter.egress({}, ir, latency_ms)
    assert len(result.provenance) == before + 1
    assert result.provenance[-1].model_id == "test-org/echo-v1"
