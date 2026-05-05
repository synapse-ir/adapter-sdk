"""Canonical IR types for the SYNAPSE adapter SDK (§1, G-C02, G-C05, G-C08)."""

from __future__ import annotations

import json
import logging
import re
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Size limit constants (G-C05)
# ---------------------------------------------------------------------------

_MB = 1024 * 1024

CONTENT_HARD_BYTES  = 10 * _MB
CONTENT_SOFT_BYTES  = 1  * _MB
VECTOR_HARD_BYTES   = 50 * _MB
VECTOR_SOFT_BYTES   = 10 * _MB
DATA_HARD_BYTES     = 5  * _MB
DATA_SOFT_BYTES     = 500 * 1024
BINARY_HARD_BYTES   = 50 * _MB
BINARY_SOFT_BYTES   = 10 * _MB
PROVENANCE_HARD_LEN = 100
PROVENANCE_SOFT_LEN = 20
TOTAL_IR_HARD_BYTES = 100 * _MB
TOTAL_IR_SOFT_BYTES = 20  * _MB
TAGS_HARD_LEN       = 50
TAGS_SOFT_LEN       = 10

# ---------------------------------------------------------------------------
# Error types (G-C06 envelope)
# ---------------------------------------------------------------------------

class IRPayloadTooLargeError(ValueError):
    """Raised when a payload field exceeds its hard size limit."""

    def __init__(
        self,
        field: str,
        limit_bytes: int,
        received_bytes: int,
        *,
        recommendation: str = "Use context_ref to store large payloads and reference by ID",
    ) -> None:
        limit_mb = limit_bytes / _MB
        received_mb = received_bytes / _MB
        message = (
            f"{field} exceeds maximum size of {limit_mb:.0f}MB "
            f"(received {received_mb:.1f}MB)"
        )
        self.envelope: dict[str, Any] = {
            "error": "IR_PAYLOAD_TOO_LARGE",
            "message": message,
            "field": field,
            "limit_bytes": limit_bytes,
            "received_bytes": received_bytes,
            "recommendation": recommendation,
        }
        super().__init__(json.dumps(self.envelope))


class IRInvalidFieldError(ValueError):
    """Raised when a string field contains a forbidden value (G-C08)."""

    def __init__(self, field: str, reason: str) -> None:
        self.envelope: dict[str, Any] = {
            "error": "IR_INVALID_FIELD",
            "field": field,
            "reason": reason,
        }
        super().__init__(json.dumps(self.envelope))


# ---------------------------------------------------------------------------
# Enumerations (§1.3.1 / §1.3.2)
# ---------------------------------------------------------------------------

class TaskType(StrEnum):
    classify     = "classify"
    extract      = "extract"
    generate     = "generate"
    summarize    = "summarize"
    embed        = "embed"
    rank         = "rank"
    validate     = "validate"
    translate    = "translate"  # type: ignore[assignment]  # shadows str.translate
    score        = "score"


class Domain(StrEnum):
    general        = "general"
    legal          = "legal"
    medical        = "medical"
    finance        = "finance"
    code           = "code"
    scientific     = "scientific"
    multilingual   = "multilingual"
    conversational = "conversational"


# ---------------------------------------------------------------------------
# Null-byte guard (G-C08)
# ---------------------------------------------------------------------------

def _reject_null_bytes(value: str, field: str) -> None:
    if "\x00" in value:
        raise IRInvalidFieldError(
            field, "null byte (\\x00) is not permitted in string fields"
        )


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class TaskHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type:         TaskType
    domain:            Domain
    priority:          int   = Field(..., ge=1, le=3)
    latency_budget_ms: int   = Field(..., ge=0)
    cost_ceiling:      Optional[float] = None
    quality_floor:     Optional[float] = Field(default=None, ge=0.0, le=1.0)
    session_id:        Optional[str]   = None
    idempotency_key:   Optional[str]   = None

    @field_validator("session_id", "idempotency_key", mode="before")
    @classmethod
    def _no_nulls(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            _reject_null_bytes(v, f"task_header.{info.field_name}")
        return v


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text:       str
    label:      str
    start:      Optional[int]   = Field(default=None, ge=0)
    end:        Optional[int]   = Field(default=None, ge=0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("text", "label", mode="before")
    @classmethod
    def _no_nulls(cls, v: str, info) -> str:
        _reject_null_bytes(v, f"entity.{info.field_name}")
        return v


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: str  # "text" | "embedding" | "structured" | "binary"

    # text
    content:         Optional[str] = None
    content_length:  Optional[int] = None
    language:        Optional[str] = None

    # embedding
    vector:          Optional[list[float]] = None
    vector_dim:      Optional[int]         = None
    embedding_model: Optional[str]         = None

    # structured
    data:       Optional[dict[str, Any]] = None
    schema_ref: Optional[str]            = None

    # binary
    binary_b64:  Optional[str] = None
    mime_type:   Optional[str] = None
    byte_length: Optional[int] = None

    # common
    context_ref: Optional[str]          = None
    entities:    Optional[list[Entity]] = None

    @field_validator("modality", mode="before")
    @classmethod
    def _valid_modality(cls, v: str) -> str:
        allowed = {"text", "embedding", "structured", "binary"}
        if v not in allowed:
            raise ValueError(f"modality must be one of {allowed!r}, got {v!r}")
        return v

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        _reject_null_bytes(v, "payload.content")
        size = len(v.encode("utf-8"))
        if size > CONTENT_HARD_BYTES:
            raise IRPayloadTooLargeError("payload.content", CONTENT_HARD_BYTES, size)
        if size > CONTENT_SOFT_BYTES:
            logger.warning(
                "payload.content exceeds soft limit of 1MB (%d bytes); consider using context_ref",
                size,
            )
        return v

    @field_validator("vector", mode="before")
    @classmethod
    def _validate_vector(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is None:
            return v
        size = len(v) * 8  # float64 = 8 bytes
        if size > VECTOR_HARD_BYTES:
            raise IRPayloadTooLargeError("payload.vector", VECTOR_HARD_BYTES, size)
        if size > VECTOR_SOFT_BYTES:
            logger.warning("payload.vector exceeds soft limit of 10MB (%d bytes)", size)
        return v

    @field_validator("data", mode="before")
    @classmethod
    def _validate_data(cls, v: Optional[dict]) -> Optional[dict]:
        if v is None:
            return v
        size = len(json.dumps(v).encode("utf-8"))
        if size > DATA_HARD_BYTES:
            raise IRPayloadTooLargeError("payload.data", DATA_HARD_BYTES, size)
        if size > DATA_SOFT_BYTES:
            logger.warning("payload.data exceeds soft limit of 500KB (%d bytes)", size)
        return v

    @field_validator("binary_b64", mode="before")
    @classmethod
    def _validate_binary(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        _reject_null_bytes(v, "payload.binary_b64")
        size = len(v.encode("utf-8"))
        if size > BINARY_HARD_BYTES:
            raise IRPayloadTooLargeError("payload.binary_b64", BINARY_HARD_BYTES, size)
        if size > BINARY_SOFT_BYTES:
            logger.warning("payload.binary_b64 exceeds soft limit of 10MB (%d bytes)", size)
        return v

    @field_validator("language", "schema_ref", "context_ref", "embedding_model", "mime_type", mode="before")
    @classmethod
    def _no_nulls_str(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            _reject_null_bytes(v, f"payload.{info.field_name}")
        return v

    @model_validator(mode="after")
    def _modality_consistency(self) -> "Payload":
        if self.modality == "text" and self.content is None:
            raise ValueError("payload.content is required when modality='text'")
        if self.modality == "embedding" and self.vector is None:
            raise ValueError("payload.vector is required when modality='embedding'")
        if self.modality == "structured" and self.data is None:
            raise ValueError("payload.data is required when modality='structured'")
        if self.modality == "binary":
            if self.binary_b64 is None:
                raise ValueError("payload.binary_b64 is required when modality='binary'")
            if self.mime_type is None:
                raise ValueError("payload.mime_type is required when modality='binary'")
        return self


class ProvenanceEntry(BaseModel):
    # frozen=True makes Pydantic reject mutations; __setattr__ re-raises as TypeError (§1.5)
    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    def __setattr__(self, name: str, value: object) -> None:
        # Pydantic frozen raises ValidationError; spec §1.5 mandates TypeError.
        try:
            super().__setattr__(name, value)
        except Exception as exc:
            raise TypeError(
                f"ProvenanceEntry is immutable — field {name!r} cannot be modified"
            ) from exc

    model_id:        str
    adapter_version: str
    confidence:      float = Field(..., ge=0.0, le=1.0)
    latency_ms:      int   = Field(..., ge=0)
    timestamp_unix:  int
    cost_usd:        Optional[float] = None
    token_count:     Optional[int]   = None
    warnings:        Optional[list[str]] = None

    @field_validator("model_id", "adapter_version", mode="before")
    @classmethod
    def _no_nulls(cls, v: str, info) -> str:
        _reject_null_bytes(v, f"provenance.{info.field_name}")
        return v

    @field_validator("warnings", mode="before")
    @classmethod
    def _no_nulls_warnings(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            for w in v:
                _reject_null_bytes(w, "provenance.warnings[]")
        return v


class ComplianceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_tags:      Optional[list[str]] = None
    pii_present:        Optional[bool]      = None
    data_residency:     Optional[list[str]] = None
    retention_policy:   Optional[str]       = None
    purpose_limitation: Optional[str]       = None

    @field_validator("required_tags", mode="before")
    @classmethod
    def _validate_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) > TAGS_HARD_LEN:
            raise ValueError(
                f"compliance_envelope.required_tags exceeds maximum of {TAGS_HARD_LEN} entries"
            )
        if len(v) > TAGS_SOFT_LEN:
            logger.warning(
                "compliance_envelope.required_tags has %d entries, soft limit is %d",
                len(v), TAGS_SOFT_LEN,
            )
        return v


# ---------------------------------------------------------------------------
# Root IR model (§1.2)
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class CanonicalIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ir_version:          str
    message_id:          str
    task_header:         TaskHeader
    payload:             Payload
    provenance:          list[ProvenanceEntry] = Field(default_factory=list)
    compliance_envelope: ComplianceEnvelope    = Field(default_factory=ComplianceEnvelope)

    @field_validator("ir_version", mode="before")
    @classmethod
    def _validate_ir_version(cls, v: str) -> str:
        _reject_null_bytes(v, "ir_version")
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"ir_version must be semver (e.g. '1.0.0'), got {v!r}")
        return v

    @field_validator("message_id", mode="before")
    @classmethod
    def _validate_message_id(cls, v: str) -> str:
        _reject_null_bytes(v, "message_id")
        if not _UUID_RE.match(v):
            raise ValueError(f"message_id must be a UUID, got {v!r}")
        return v

    @field_validator("provenance", mode="before")
    @classmethod
    def _validate_provenance_len(cls, v: list) -> list:
        if len(v) > PROVENANCE_HARD_LEN:
            raise ValueError(
                f"provenance array exceeds maximum of {PROVENANCE_HARD_LEN} entries "
                f"(received {len(v)})"
            )
        if len(v) > PROVENANCE_SOFT_LEN:
            logger.warning(
                "provenance array has %d entries, soft limit is %d",
                len(v), PROVENANCE_SOFT_LEN,
            )
        return v

    @model_validator(mode="after")
    def _total_size_check(self) -> "CanonicalIR":
        size = len(self.to_json().encode("utf-8"))
        if size > TOTAL_IR_HARD_BYTES:
            raise IRPayloadTooLargeError("canonical_ir", TOTAL_IR_HARD_BYTES, size)
        if size > TOTAL_IR_SOFT_BYTES:
            logger.warning("Serialized IR is %d bytes, exceeds 20MB soft limit", size)
        return self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def copy(self, **kwargs: Any) -> "CanonicalIR":
        """Shallow copy — new top-level model instance, shared sub-objects."""
        return self.model_copy()

    def clone(self) -> "CanonicalIR":
        """Deep copy with no shared state."""
        return self.model_validate(self.model_dump())

    def to_json(self) -> str:
        """Serialize to compact JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str | bytes) -> "CanonicalIR":
        """Deserialize from JSON, running all validators."""
        return cls.model_validate_json(data)
