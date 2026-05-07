"""Tests for synapse_sdk.testing fixtures — §9 G-S06."""

import synapse_sdk.testing as testing_module
from synapse_sdk.testing import (
    ALL_FIXTURES,
    BINARY_PAYLOAD,
    EMPTY_COMPLIANCE,
    FINANCE_GENERATE_SOX,
    FULL_COMPLIANCE,
    GENERAL_EMBED_LARGE,
    LEGAL_EXTRACT_BASIC,
    LEGAL_EXTRACT_PII,
    MAX_PROVENANCE_CHAIN,
    MEDICAL_CLASSIFY_HIPAA,
    MINIMAL_VALID_IR,
    MULTILINGUAL_TRANSLATE,
    PARTIAL_FAILURE_POLICY,
    RANK_WITH_PRIOR_PROVENANCE,
    SCORE_TASK,
    SESSION_WITH_CONTEXT_REF,
    STRUCTURED_PAYLOAD,
    TIGHT_LATENCY_BUDGET,
    TRACE_CONTEXT_SET,
    VALIDATE_TASK,
    ZERO_LATENCY_BUDGET,
)
from synapse_sdk.types import CanonicalIR

# Suppress "unused import" warnings — the bare imports above are themselves
# the import-succeeds assertion for all 20 fixture names.
_ = (
    BINARY_PAYLOAD, GENERAL_EMBED_LARGE, MULTILINGUAL_TRANSLATE,
    PARTIAL_FAILURE_POLICY, SCORE_TASK, SESSION_WITH_CONTEXT_REF,
    STRUCTURED_PAYLOAD, TRACE_CONTEXT_SET, VALIDATE_TASK,
)


class TestAllFixturesCatalogue:

    def test_all_fixtures_contains_exactly_20_items(self):
        assert len(ALL_FIXTURES) == 20

    def test_all_fixtures_are_canonical_ir_instances(self):
        for fixture in ALL_FIXTURES:
            assert isinstance(fixture, CanonicalIR), (
                f"{fixture!r} is not a CanonicalIR instance"
            )

    def test_all_20_fixture_names_importable_from_testing_module(self):
        expected = [
            "LEGAL_EXTRACT_BASIC", "LEGAL_EXTRACT_PII", "MEDICAL_CLASSIFY_HIPAA",
            "FINANCE_GENERATE_SOX", "GENERAL_EMBED_LARGE", "MULTILINGUAL_TRANSLATE",
            "RANK_WITH_PRIOR_PROVENANCE", "ZERO_LATENCY_BUDGET", "TIGHT_LATENCY_BUDGET",
            "MAX_PROVENANCE_CHAIN", "EMPTY_COMPLIANCE", "FULL_COMPLIANCE",
            "SESSION_WITH_CONTEXT_REF", "STRUCTURED_PAYLOAD", "BINARY_PAYLOAD",
            "VALIDATE_TASK", "SCORE_TASK", "PARTIAL_FAILURE_POLICY",
            "TRACE_CONTEXT_SET", "MINIMAL_VALID_IR",
        ]
        for name in expected:
            assert hasattr(testing_module, name), (
                f"{name!r} not found in synapse_sdk.testing"
            )


class TestSpecificFixtures:

    def test_legal_extract_basic_task_type_and_domain(self):
        assert LEGAL_EXTRACT_BASIC.task_header.task_type == "extract"
        assert LEGAL_EXTRACT_BASIC.task_header.domain == "legal"

    def test_legal_extract_pii_has_pii_present_true(self):
        assert LEGAL_EXTRACT_PII.compliance_envelope.pii_present is True

    def test_medical_classify_hipaa_has_hipaa_tag(self):
        tags = MEDICAL_CLASSIFY_HIPAA.compliance_envelope.required_tags
        assert tags is not None
        assert "hipaa" in tags

    def test_finance_generate_sox_has_sox_tag(self):
        tags = FINANCE_GENERATE_SOX.compliance_envelope.required_tags
        assert tags is not None
        assert "sox" in tags

    def test_zero_latency_budget_is_zero(self):
        assert ZERO_LATENCY_BUDGET.task_header.latency_budget_ms == 0

    def test_tight_latency_budget_is_ten(self):
        assert TIGHT_LATENCY_BUDGET.task_header.latency_budget_ms == 10

    def test_empty_compliance_has_all_fields_none(self):
        env = EMPTY_COMPLIANCE.compliance_envelope
        assert env.required_tags is None
        assert env.pii_present is None
        assert env.data_residency is None
        assert env.retention_policy is None
        assert env.purpose_limitation is None

    def test_full_compliance_required_tags_contain_key_values(self):
        tags = FULL_COMPLIANCE.compliance_envelope.required_tags
        assert tags is not None
        for tag in ("gdpr", "hipaa", "sox", "pci-dss"):
            assert tag in tags, f"Expected tag {tag!r} missing from {tags}"

    def test_minimal_valid_ir_loads_without_error(self):
        assert isinstance(MINIMAL_VALID_IR, CanonicalIR)

    def test_minimal_valid_ir_has_no_optional_fields_set(self):
        ir = MINIMAL_VALID_IR
        assert ir.provenance == []
        assert ir.compliance_envelope.required_tags is None
        assert ir.compliance_envelope.pii_present is None
        assert ir.task_header.cost_ceiling is None
        assert ir.task_header.session_id is None
        assert ir.task_header.trace_context is None

    def test_max_provenance_chain_has_exactly_20_entries(self):
        assert len(MAX_PROVENANCE_CHAIN.provenance) == 20

    def test_rank_with_prior_provenance_has_exactly_5_entries(self):
        assert len(RANK_WITH_PRIOR_PROVENANCE.provenance) == 5
