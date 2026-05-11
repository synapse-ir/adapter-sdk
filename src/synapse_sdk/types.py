"""Canonical IR types for the SYNAPSE adapter SDK (§1, G-C02, G-C05, G-C08)."""

from __future__ import annotations

import json
import logging
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

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
    transcribe   = "transcribe"


class Domain(StrEnum):
    general        = "general"
    legal          = "legal"
    medical        = "medical"
    finance        = "finance"
    code           = "code"
    scientific     = "scientific"
    multilingual   = "multilingual"
    conversational = "conversational"
    audio          = "audio"
    document       = "document"
    multimodal     = "multimodal"
    vision         = "vision"


class FailurePolicy(StrEnum):
    """Pipeline failure semantics — added in §9 G-S02.

    abort    (default) — any stage failure aborts the pipeline.
    partial  — failed stages are skipped; returns PartialCompletionResponse.
    fallback — tries fallback model from slot assignment before partial.
    """
    abort    = "abort"
    partial  = "partial"
    fallback = "fallback"


class BranchRole(StrEnum):
    """Role of a ProvenanceEntry in a parallel pipeline — §9 G-S03.

    Sequential pipelines leave branch_id / branch_role absent.
    Phase 2 fan-out/fan-in will populate these fields; the flat-array
    provenance design means no IR version bump is required.
    """
    source = "source"   # stage that initiated the fan-out
    branch = "branch"   # a parallel branch stage
    merge  = "merge"    # stage that aggregated branch results


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

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# W3C Trace Context traceparent: 00-{32hex}-{16hex}-{2hex}
_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$",
    re.IGNORECASE,
)


class TraceContext(BaseModel):
    """W3C Trace Context fields propagated through the IR — §9 G-S01.

    Presence is optional. When absent, tracing.propagate_trace_context()
    will synthesise a new root trace.
    """
    model_config = ConfigDict(extra="forbid")

    traceparent: str
    tracestate:  str | None = None

    @field_validator("traceparent", mode="before")
    @classmethod
    def _validate_traceparent(cls, v: str) -> str:
        _reject_null_bytes(v, "trace_context.traceparent")
        if not _TRACEPARENT_RE.match(v):
            raise ValueError(
                f"traceparent must be W3C format '00-{{trace_id}}-{{parent_id}}-{{flags}}', "
                f"got {v!r}"
            )
        return v.lower()

    @field_validator("tracestate", mode="before")
    @classmethod
    def _no_nulls_tracestate(cls, v: str | None) -> str | None:
        if v is not None:
            _reject_null_bytes(v, "trace_context.tracestate")
        return v


class TaskHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type:         TaskType
    domain:            Domain
    priority:          int   = Field(..., ge=1, le=3)
    latency_budget_ms: int   = Field(..., ge=0)
    cost_ceiling:      float | None = None
    quality_floor:     float | None = Field(default=None, ge=0.0, le=1.0)
    session_id:        str | None   = None
    idempotency_key:   str | None   = None
    query:             str | None   = None
    # G-S01 — W3C Trace Context propagation
    trace_context:     TraceContext | None = None
    # G-S02 — pipeline failure semantics ('abort' preserves current behaviour)
    failure_policy:    FailurePolicy = FailurePolicy.abort
    # zero-shot classification — candidate labels supplied by the caller
    candidate_labels:  list[str] | None = None

    @field_validator("session_id", "idempotency_key", "query", mode="before")
    @classmethod
    def _no_nulls(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is not None:
            _reject_null_bytes(v, f"task_header.{info.field_name}")
        return v


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text:       str
    label:      str
    start:      int | None   = Field(default=None, ge=0)
    end:        int | None   = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("text", "label", mode="before")
    @classmethod
    def _no_nulls(cls, v: str, info: ValidationInfo) -> str:
        _reject_null_bytes(v, f"entity.{info.field_name}")
        return v


class Classification(BaseModel):
    """A classification label and its softmax confidence score."""
    model_config = ConfigDict(extra="forbid")

    label: str
    score: float = Field(..., ge=0.0, le=1.0)

    @field_validator("label", mode="before")
    @classmethod
    def _no_nulls(cls, v: str) -> str:
        _reject_null_bytes(v, "classification.label")
        return v


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: str  # "text" | "embedding" | "structured" | "binary"

    # text
    content:         str | None = None
    content_length:  int | None = None
    language:        str | None = None

    # embedding
    vector:          list[float] | None = None
    vector_dim:      int | None         = None
    embedding_model: str | None         = None

    # structured
    data:       dict[str, Any] | None = None
    schema_ref: str | None            = None

    # binary
    binary_b64:  str | None = None
    mime_type:   str | None = None
    byte_length: int | None = None

    # common
    context_ref: str | None                  = None
    entities:    list[Entity] | None          = None
    labels:      list[Classification] | None  = None
    score:       float | None                 = Field(default=None, ge=0.0, le=1.0)

    @field_validator("modality", mode="before")
    @classmethod
    def _valid_modality(cls, v: str) -> str:
        allowed = {"text", "embedding", "structured", "binary"}
        if v not in allowed:
            raise ValueError(f"modality must be one of {allowed!r}, got {v!r}")
        return v

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content(cls, v: str | None) -> str | None:
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
    def _validate_vector(cls, v: list[float] | None) -> list[float] | None:
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
    def _validate_data(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
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
    def _validate_binary(cls, v: str | None) -> str | None:
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
    def _no_nulls_str(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is not None:
            _reject_null_bytes(v, f"payload.{info.field_name}")
        return v

    @model_validator(mode="after")
    def _modality_consistency(self) -> Payload:
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
    cost_usd:        float | None = None
    token_count:     int | None   = None
    warnings:        list[str] | None = None
    # G-S03 — parallel branch anchor points (absent for sequential pipelines)
    branch_id:       str | None        = None
    branch_role:     BranchRole | None = None

    @field_validator("model_id", "adapter_version", mode="before")
    @classmethod
    def _no_nulls(cls, v: str, info: ValidationInfo) -> str:
        _reject_null_bytes(v, f"provenance.{info.field_name}")
        return v

    @field_validator("warnings", mode="before")
    @classmethod
    def _no_nulls_warnings(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for w in v:
                _reject_null_bytes(w, "provenance.warnings[]")
        return v

    @field_validator("branch_id", mode="before")
    @classmethod
    def _validate_branch_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        _reject_null_bytes(v, "provenance.branch_id")
        if not _UUID_RE.match(v):
            raise ValueError(f"provenance.branch_id must be a UUID v4, got {v!r}")
        return v


class ComplianceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_tags:      list[str] | None = None
    pii_present:        bool | None      = None
    data_residency:     list[str] | None = None
    retention_policy:   str | None       = None
    purpose_limitation: str | None       = None

    @field_validator("required_tags", mode="before")
    @classmethod
    def _validate_tags(cls, v: list[str] | None) -> list[str] | None:
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
    def _validate_provenance_len(cls, v: list[Any]) -> list[Any]:
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
    def _total_size_check(self) -> CanonicalIR:
        size = len(self.to_json().encode("utf-8"))
        if size > TOTAL_IR_HARD_BYTES:
            raise IRPayloadTooLargeError("canonical_ir", TOTAL_IR_HARD_BYTES, size)
        if size > TOTAL_IR_SOFT_BYTES:
            logger.warning("Serialized IR is %d bytes, exceeds 20MB soft limit", size)
        return self

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def copy(self, **kwargs: Any) -> CanonicalIR:
        """Shallow copy — new top-level model instance, shared sub-objects."""
        return self.model_copy()

    def clone(self) -> CanonicalIR:
        """Deep copy with no shared state."""
        return self.model_validate(self.model_dump())

    def to_json(self) -> str:
        """Serialize to compact JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str | bytes) -> CanonicalIR:
        """Deserialize from JSON, running all validators."""
        return cls.model_validate_json(data)


# ---------------------------------------------------------------------------
# G-S02 — Partial pipeline failure response types (§9 G-S02)
# ---------------------------------------------------------------------------

class FailedStage(BaseModel):
    """Describes a single pipeline stage that failed under failure_policy='partial'."""
    model_config = ConfigDict(extra="forbid")

    model_id:    str
    error:       str
    detail:      str | None = None
    stage_index: int | None = Field(default=None, ge=0)

    @field_validator("model_id", "error", mode="before")
    @classmethod
    def _no_nulls(cls, v: str, info: ValidationInfo) -> str:
        _reject_null_bytes(v, f"failed_stage.{info.field_name}")
        return v


class PartialCompletionResponse(BaseModel):
    """Returned when failure_policy='partial' and at least one stage failed.

    completed_stages lists model_id values that succeeded.
    failed_stages   lists FailedStage records for each failure.
    payload         is the best available result from completed stages.
    provenance      contains entries from completed stages only.
    """
    model_config = ConfigDict(extra="forbid")

    partial_completion: bool = True
    completed_stages:   list[str]
    failed_stages:      list[FailedStage]
    payload:            Payload
    provenance:         list[ProvenanceEntry] = Field(default_factory=list)
