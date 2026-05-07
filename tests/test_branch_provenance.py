"""Tests for G-S03 — Parallel Branch Provenance (ProvenanceEntry extension)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from synapse_sdk.types import (
    BranchRole,
    CanonicalIR,
    Domain,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BRANCH_UUID = "a1b2c3d4-e5f6-4000-8000-000000000001"
_BRANCH_UUID2 = "a1b2c3d4-e5f6-4000-8000-000000000002"


def _prov(model_id: str, **kwargs) -> ProvenanceEntry:
    return ProvenanceEntry(
        model_id=model_id,
        adapter_version="1.0.0",
        confidence=0.9,
        latency_ms=100,
        timestamp_unix=1_700_000_000,
        **kwargs,
    )


def _make_ir(provenance: list[ProvenanceEntry] | None = None) -> CanonicalIR:
    return CanonicalIR(
        ir_version="1.0.0",
        message_id="00000000-0000-4000-8000-000000000099",
        task_header=TaskHeader(
            task_type=TaskType.extract,
            domain=Domain.legal,
            priority=1,
            latency_budget_ms=500,
        ),
        payload=Payload(modality="text", content="data"),
        provenance=provenance or [],
    )


# ---------------------------------------------------------------------------
# BranchRole enum
# ---------------------------------------------------------------------------

class TestBranchRoleEnum:
    def test_values(self):
        assert BranchRole.source == "source"
        assert BranchRole.branch == "branch"
        assert BranchRole.merge  == "merge"

    def test_from_string(self):
        assert BranchRole("source") is BranchRole.source
        assert BranchRole("branch") is BranchRole.branch
        assert BranchRole("merge")  is BranchRole.merge

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            BranchRole("fan-out")


# ---------------------------------------------------------------------------
# ProvenanceEntry.branch_id and branch_role — absence (backward compat)
# ---------------------------------------------------------------------------

class TestProvEntrySansFields:
    def test_sequential_pipeline_no_branch_fields(self):
        """Sequential pipelines must work with branch_id/branch_role absent."""
        p = _prov("model-a")
        assert p.branch_id is None
        assert p.branch_role is None

    def test_existing_ir_round_trips_without_branch_fields(self):
        ir = _make_ir([_prov("m1"), _prov("m2")])
        ir2 = CanonicalIR.from_json(ir.to_json())
        for entry in ir2.provenance:
            assert entry.branch_id is None
            assert entry.branch_role is None

    def test_json_omits_null_branch_fields(self):
        p = _prov("model-a")
        data = json.loads(p.model_dump_json())
        # Pydantic serialises None as null; verify absence of non-null values
        assert data.get("branch_id") is None
        assert data.get("branch_role") is None


# ---------------------------------------------------------------------------
# ProvenanceEntry.branch_id validation
# ---------------------------------------------------------------------------

class TestBranchIdValidation:
    def test_valid_uuid_accepted(self):
        p = _prov("model-a", branch_id=_BRANCH_UUID)
        assert p.branch_id == _BRANCH_UUID

    def test_uuid_uppercase_accepted(self):
        p = _prov("model-a", branch_id=_BRANCH_UUID.upper())
        # UUID comparison is case-insensitive via the regex
        assert p.branch_id is not None

    def test_invalid_uuid_rejected(self):
        with pytest.raises((ValidationError, ValueError)):
            _prov("model-a", branch_id="not-a-uuid")

    def test_null_byte_in_branch_id_rejected(self):
        with pytest.raises(Exception):
            _prov("model-a", branch_id="a1b2c3d4-e5f6-4000-8000-00000000\x0001")

    def test_none_branch_id_accepted(self):
        p = _prov("model-a", branch_id=None)
        assert p.branch_id is None


# ---------------------------------------------------------------------------
# ProvenanceEntry.branch_role
# ---------------------------------------------------------------------------

class TestBranchRoleField:
    def test_source_role(self):
        p = _prov("fanout-model", branch_id=_BRANCH_UUID, branch_role=BranchRole.source)
        assert p.branch_role == BranchRole.source

    def test_branch_role(self):
        p = _prov("branch-model", branch_id=_BRANCH_UUID, branch_role=BranchRole.branch)
        assert p.branch_role == BranchRole.branch

    def test_merge_role(self):
        p = _prov("merge-model", branch_id=_BRANCH_UUID, branch_role=BranchRole.merge)
        assert p.branch_role == BranchRole.merge

    def test_role_from_string(self):
        p = _prov("m", branch_id=_BRANCH_UUID, branch_role="branch")
        assert p.branch_role == BranchRole.branch

    def test_invalid_role_rejected(self):
        with pytest.raises((ValidationError, ValueError)):
            _prov("m", branch_id=_BRANCH_UUID, branch_role="fan-out")

    def test_branch_role_without_branch_id(self):
        """branch_role can be set without branch_id (schema allows it)."""
        p = _prov("m", branch_role=BranchRole.merge)
        assert p.branch_role == BranchRole.merge
        assert p.branch_id is None


# ---------------------------------------------------------------------------
# ProvenanceEntry immutability is preserved with new fields
# ---------------------------------------------------------------------------

class TestImmutabilityPreserved:
    def test_branch_id_mutation_raises_type_error(self):
        p = _prov("m", branch_id=_BRANCH_UUID)
        with pytest.raises(TypeError):
            p.branch_id = _BRANCH_UUID2  # type: ignore[misc]

    def test_branch_role_mutation_raises_type_error(self):
        p = _prov("m", branch_id=_BRANCH_UUID, branch_role=BranchRole.branch)
        with pytest.raises(TypeError):
            p.branch_role = BranchRole.merge  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Round-trip JSON with branch fields
# ---------------------------------------------------------------------------

class TestBranchFieldsRoundTrip:
    def test_single_entry_with_branch_fields(self):
        p = _prov("model-b", branch_id=_BRANCH_UUID, branch_role=BranchRole.branch)
        data = p.model_dump_json()
        p2 = ProvenanceEntry.model_validate_json(data)
        assert p2.branch_id == _BRANCH_UUID
        assert p2.branch_role == BranchRole.branch

    def test_ir_round_trip_with_branch_provenance(self):
        ir = _make_ir([
            _prov("fanout", branch_id=_BRANCH_UUID, branch_role=BranchRole.source),
            _prov("left",   branch_id=_BRANCH_UUID, branch_role=BranchRole.branch),
            _prov("right",  branch_id=_BRANCH_UUID, branch_role=BranchRole.branch),
            _prov("merger", branch_id=_BRANCH_UUID, branch_role=BranchRole.merge),
        ])
        ir2 = CanonicalIR.from_json(ir.to_json())
        assert ir2.provenance[0].branch_role == BranchRole.source
        assert ir2.provenance[1].branch_role == BranchRole.branch
        assert ir2.provenance[2].branch_role == BranchRole.branch
        assert ir2.provenance[3].branch_role == BranchRole.merge
        # All share the same branch_id
        for entry in ir2.provenance:
            assert entry.branch_id is not None

    def test_mixed_sequential_and_branch_entries(self):
        """Sequential entries and branch entries can coexist in the same chain."""
        ir = _make_ir([
            _prov("seq-stage-1"),   # no branch fields
            _prov("fanout", branch_id=_BRANCH_UUID, branch_role=BranchRole.source),
            _prov("branch-a", branch_id=_BRANCH_UUID, branch_role=BranchRole.branch),
            _prov("branch-b", branch_id=_BRANCH_UUID, branch_role=BranchRole.branch),
            _prov("merger", branch_id=_BRANCH_UUID, branch_role=BranchRole.merge),
            _prov("seq-stage-2"),   # no branch fields (post-merge)
        ])
        ir2 = CanonicalIR.from_json(ir.to_json())
        assert ir2.provenance[0].branch_id is None
        assert ir2.provenance[5].branch_id is None
        assert ir2.provenance[1].branch_role == BranchRole.source


# ---------------------------------------------------------------------------
# Flat-array design — multiple concurrent branches
# ---------------------------------------------------------------------------

class TestMultipleBranchGroups:
    def test_two_independent_branches_distinct_branch_ids(self):
        """Two concurrent fan-outs use distinct branch_ids."""
        ir = _make_ir([
            _prov("fanout-a", branch_id=_BRANCH_UUID,  branch_role=BranchRole.source),
            _prov("b1",       branch_id=_BRANCH_UUID,  branch_role=BranchRole.branch),
            _prov("merge-a",  branch_id=_BRANCH_UUID,  branch_role=BranchRole.merge),
            _prov("fanout-b", branch_id=_BRANCH_UUID2, branch_role=BranchRole.source),
            _prov("b2",       branch_id=_BRANCH_UUID2, branch_role=BranchRole.branch),
            _prov("merge-b",  branch_id=_BRANCH_UUID2, branch_role=BranchRole.merge),
        ])
        ir2 = CanonicalIR.from_json(ir.to_json())
        branch_a_ids = {e.branch_id for e in ir2.provenance[:3]}
        branch_b_ids = {e.branch_id for e in ir2.provenance[3:]}
        assert branch_a_ids == {_BRANCH_UUID}
        assert branch_b_ids == {_BRANCH_UUID2}
        assert branch_a_ids.isdisjoint(branch_b_ids)
