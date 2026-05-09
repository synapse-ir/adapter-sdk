"""Tests for CanonicalIR and related types (§1, G-C05, G-C08)."""

import json

import pytest
from pydantic import ValidationError

from synapse_sdk.types import (
    CanonicalIR,
    Domain,
    IRInvalidFieldError,
    IRPayloadTooLargeError,
    ProvenanceEntry,
    TaskType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_HEADER = {
    "task_type": "extract",
    "domain": "legal",
    "priority": 1,
    "latency_budget_ms": 180,
    "cost_ceiling": 0.004,
    "quality_floor": 0.85,
    "session_id": "sess_a4f8b2c1d9e3",
}

VALID_PAYLOAD = {
    "modality": "text",
    "content": "The licensor grants a non-exclusive, worldwide, royalty-free license...",
    "content_length": 68,
    "language": "en-US",
}

VALID_PROVENANCE = [
    {
        "model_id": "ner-legal-v2.1",
        "adapter_version": "1.2.0",
        "confidence": 0.94,
        "latency_ms": 43,
        "timestamp_unix": 1746384021,
        "cost_usd": 0.00009,
        "token_count": 512,
    }
]

VALID_COMPLIANCE = {
    "required_tags": ["gdpr-eu"],
    "pii_present": False,
    "data_residency": ["EU"],
    "retention_policy": "session",
}

VALID_IR = {
    "ir_version": "1.0.0",
    "message_id": "019123ab-dead-7f00-beef-cafe0000a001",
    "task_header": VALID_HEADER,
    "payload": VALID_PAYLOAD,
    "provenance": VALID_PROVENANCE,
    "compliance_envelope": VALID_COMPLIANCE,
}


def make_ir(**overrides) -> CanonicalIR:
    data = {**VALID_IR, **overrides}
    return CanonicalIR.model_validate(data)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_to_json_from_json(self):
        ir = make_ir()
        restored = CanonicalIR.from_json(ir.to_json())
        assert restored.message_id == ir.message_id
        assert restored.task_header.task_type == TaskType.extract
        assert restored.task_header.domain == Domain.legal
        assert restored.provenance[0].model_id == "ner-legal-v2.1"

    def test_to_json_is_valid_json(self):
        ir = make_ir()
        parsed = json.loads(ir.to_json())
        assert parsed["ir_version"] == "1.0.0"
        assert parsed["message_id"] == "019123ab-dead-7f00-beef-cafe0000a001"

    def test_clone_is_independent(self):
        ir = make_ir()
        cloned = ir.clone()
        assert cloned.message_id == ir.message_id
        assert cloned is not ir

    def test_copy_returns_new_instance(self):
        ir = make_ir()
        copied = ir.copy()
        assert copied.message_id == ir.message_id
        assert copied is not ir

    def test_from_json_bytes(self):
        ir = make_ir()
        restored = CanonicalIR.from_json(ir.to_json().encode("utf-8"))
        assert restored.message_id == ir.message_id

    def test_empty_provenance_valid(self):
        ir = make_ir(provenance=[])
        assert ir.provenance == []

    def test_empty_compliance_envelope_valid(self):
        ir = make_ir(compliance_envelope={})
        assert ir.compliance_envelope.pii_present is None


# ---------------------------------------------------------------------------
# Required-field validation
# ---------------------------------------------------------------------------

class TestRequiredFields:
    @pytest.mark.parametrize("missing_key", [
        "ir_version", "message_id", "task_header", "payload",
    ])
    def test_missing_top_level_field(self, missing_key):
        data = {k: v for k, v in VALID_IR.items() if k != missing_key}
        with pytest.raises(ValidationError):
            CanonicalIR.model_validate(data)

    def test_missing_task_type(self):
        header = {k: v for k, v in VALID_HEADER.items() if k != "task_type"}
        with pytest.raises(ValidationError):
            make_ir(task_header=header)

    def test_missing_domain(self):
        header = {k: v for k, v in VALID_HEADER.items() if k != "domain"}
        with pytest.raises(ValidationError):
            make_ir(task_header=header)

    def test_missing_priority(self):
        header = {k: v for k, v in VALID_HEADER.items() if k != "priority"}
        with pytest.raises(ValidationError):
            make_ir(task_header=header)

    def test_missing_latency_budget_ms(self):
        header = {k: v for k, v in VALID_HEADER.items() if k != "latency_budget_ms"}
        with pytest.raises(ValidationError):
            make_ir(task_header=header)

    def test_text_payload_missing_content(self):
        with pytest.raises(ValidationError, match="content is required"):
            make_ir(payload={"modality": "text"})

    def test_embedding_payload_missing_vector(self):
        with pytest.raises(ValidationError, match="vector is required"):
            make_ir(payload={"modality": "embedding"})

    def test_structured_payload_missing_data(self):
        with pytest.raises(ValidationError, match="data is required"):
            make_ir(payload={"modality": "structured"})

    def test_binary_payload_missing_binary_b64(self):
        with pytest.raises(ValidationError, match="binary_b64 is required"):
            make_ir(payload={"modality": "binary", "mime_type": "image/png"})

    def test_binary_payload_missing_mime_type(self):
        with pytest.raises(ValidationError, match="mime_type is required"):
            make_ir(payload={"modality": "binary", "binary_b64": "abc=="})


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------

class TestEnumValidation:
    def test_invalid_task_type(self):
        header = {**VALID_HEADER, "task_type": "hallucinate"}
        with pytest.raises(ValidationError):
            make_ir(task_header=header)

    def test_invalid_domain(self):
        header = {**VALID_HEADER, "domain": "underwater_basket_weaving"}
        with pytest.raises(ValidationError):
            make_ir(task_header=header)

    def test_invalid_modality(self):
        with pytest.raises(ValidationError, match="modality must be one of"):
            make_ir(payload={**VALID_PAYLOAD, "modality": "audio"})

    @pytest.mark.parametrize("task_type", list(TaskType))
    def test_all_task_types_valid(self, task_type):
        header = {**VALID_HEADER, "task_type": task_type}
        ir = make_ir(task_header=header)
        assert ir.task_header.task_type == task_type

    @pytest.mark.parametrize("domain", list(Domain))
    def test_all_domains_valid(self, domain):
        header = {**VALID_HEADER, "domain": domain}
        ir = make_ir(task_header=header)
        assert ir.task_header.domain == domain

    def test_priority_out_of_range(self):
        with pytest.raises(ValidationError):
            make_ir(task_header={**VALID_HEADER, "priority": 4})

    def test_priority_zero(self):
        with pytest.raises(ValidationError):
            make_ir(task_header={**VALID_HEADER, "priority": 0})


# ---------------------------------------------------------------------------
# Size-limit enforcement (G-C05)
# ---------------------------------------------------------------------------

class TestSizeLimits:
    def test_content_exceeds_10mb_raises(self):
        big = "x" * (10 * 1024 * 1024 + 1)
        with pytest.raises((ValidationError, IRPayloadTooLargeError)) as exc_info:
            make_ir(payload={**VALID_PAYLOAD, "content": big})
        # The error message should reference IR_PAYLOAD_TOO_LARGE
        assert "IR_PAYLOAD_TOO_LARGE" in str(exc_info.value)

    def test_content_under_10mb_valid(self):
        ok = "x" * (10 * 1024 * 1024 - 1)
        ir = make_ir(payload={**VALID_PAYLOAD, "content": ok})
        assert len(ir.payload.content) == len(ok)

    def test_vector_exceeds_50mb_raises(self):
        # 50MB / 8 bytes per float = 6_553_600 floats; add 1 to exceed
        big_vector = [1.0] * (50 * 1024 * 1024 // 8 + 1)
        with pytest.raises((ValidationError, IRPayloadTooLargeError)) as exc_info:
            make_ir(payload={"modality": "embedding", "vector": big_vector})
        assert "IR_PAYLOAD_TOO_LARGE" in str(exc_info.value)

    def test_data_exceeds_5mb_raises(self):
        big_data = {"key": "v" * (5 * 1024 * 1024)}
        with pytest.raises((ValidationError, IRPayloadTooLargeError)) as exc_info:
            make_ir(payload={"modality": "structured", "data": big_data})
        assert "IR_PAYLOAD_TOO_LARGE" in str(exc_info.value)

    def test_provenance_exceeds_100_entries_raises(self):
        entry = VALID_PROVENANCE[0]
        with pytest.raises(ValidationError):
            make_ir(provenance=[entry] * 101)

    def test_provenance_100_entries_valid(self):
        entry = VALID_PROVENANCE[0]
        ir = make_ir(provenance=[entry] * 100)
        assert len(ir.provenance) == 100


# ---------------------------------------------------------------------------
# Null-byte injection defense (G-C08)
# ---------------------------------------------------------------------------

class TestNullByteRejection:
    def _assert_null_field_error(self, exc_info):
        assert "IR_INVALID_FIELD" in str(exc_info.value)

    def test_null_byte_in_content(self):
        with pytest.raises((ValidationError, IRInvalidFieldError)) as exc_info:
            make_ir(payload={**VALID_PAYLOAD, "content": "hello\x00world"})
        self._assert_null_field_error(exc_info)

    def test_null_byte_in_ir_version(self):
        with pytest.raises((ValidationError, IRInvalidFieldError)) as exc_info:
            make_ir(ir_version="1.0\x000")
        assert "IR_INVALID_FIELD" in str(exc_info.value) or "ir_version" in str(exc_info.value)

    def test_null_byte_in_message_id(self):
        with pytest.raises((ValidationError, IRInvalidFieldError)):
            make_ir(message_id="019123ab-dead-7f00-\x00eef-cafe0000a001")

    def test_null_byte_in_session_id(self):
        with pytest.raises((ValidationError, IRInvalidFieldError)):
            make_ir(task_header={**VALID_HEADER, "session_id": "sess\x00abc"})

    def test_null_byte_in_model_id(self):
        bad_prov = [{**VALID_PROVENANCE[0], "model_id": "bad\x00model"}]
        with pytest.raises((ValidationError, IRInvalidFieldError)):
            make_ir(provenance=bad_prov)

    def test_null_byte_in_entity_text(self):
        payload_with_entity = {
            **VALID_PAYLOAD,
            "entities": [{"text": "bad\x00entity", "label": "ORG"}],
        }
        with pytest.raises((ValidationError, IRInvalidFieldError)):
            make_ir(payload=payload_with_entity)

    def test_null_byte_in_language(self):
        with pytest.raises((ValidationError, IRInvalidFieldError)):
            make_ir(payload={**VALID_PAYLOAD, "language": "en\x00US"})

    def test_null_byte_in_provenance_warning(self):
        bad_prov = [{**VALID_PROVENANCE[0], "warnings": ["ok", "bad\x00warning"]}]
        with pytest.raises((ValidationError, IRInvalidFieldError)):
            make_ir(provenance=bad_prov)


# ---------------------------------------------------------------------------
# ProvenanceEntry immutability (§1.5)
# ---------------------------------------------------------------------------

class TestProvenanceImmutability:
    def test_mutation_raises_type_error(self):
        entry = ProvenanceEntry(**VALID_PROVENANCE[0])
        with pytest.raises(TypeError):
            entry.model_id = "tampered"  # type: ignore[misc]

    def test_attribute_access_works(self):
        entry = ProvenanceEntry(**VALID_PROVENANCE[0])
        assert entry.model_id == "ner-legal-v2.1"
        assert entry.confidence == 0.94


# ---------------------------------------------------------------------------
# Additional valid-IR coverage
# ---------------------------------------------------------------------------

class TestValidConstruction:
    def test_embedding_ir(self):
        ir = make_ir(
            payload={"modality": "embedding", "vector": [0.1, 0.2, 0.3], "vector_dim": 3}
        )
        assert ir.payload.modality == "embedding"
        assert ir.payload.vector == [0.1, 0.2, 0.3]

    def test_structured_ir(self):
        ir = make_ir(
            payload={"modality": "structured", "data": {"key": "value"}}
        )
        assert ir.payload.data == {"key": "value"}

    def test_binary_ir(self):
        ir = make_ir(
            payload={"modality": "binary", "binary_b64": "aGVsbG8=", "mime_type": "image/png"}
        )
        assert ir.payload.mime_type == "image/png"

    def test_optional_fields_omitted(self):
        ir = make_ir(
            task_header={
                "task_type": "generate",
                "domain": "general",
                "priority": 2,
                "latency_budget_ms": 0,
            }
        )
        assert ir.task_header.cost_ceiling is None
        assert ir.task_header.quality_floor is None

    def test_ir_version_semver_validated(self):
        with pytest.raises(ValidationError, match="semver"):
            make_ir(ir_version="1.0")

    def test_message_id_uuid_validated(self):
        with pytest.raises(ValidationError, match="UUID"):
            make_ir(message_id="not-a-uuid")
