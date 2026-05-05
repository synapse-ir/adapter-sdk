"""synapse-adapter-sdk public API."""

from synapse_sdk.base import AdapterBase, AdapterConfigurationError
from synapse_sdk.types import (
    CanonicalIR,
    ComplianceEnvelope,
    Domain,
    Entity,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
)
from synapse_sdk.validator import (
    AdapterValidationError,
    AdapterValidationResult,
    AdapterValidator,
    Severity,
    ValidationFailure,
)

__all__ = [
    # base
    "AdapterBase",
    "AdapterConfigurationError",
    # types
    "CanonicalIR",
    "ComplianceEnvelope",
    "Domain",
    "Entity",
    "Payload",
    "ProvenanceEntry",
    "TaskHeader",
    "TaskType",
    # validator
    "AdapterValidationError",
    "AdapterValidationResult",
    "AdapterValidator",
    "Severity",
    "ValidationFailure",
]
