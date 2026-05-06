"""synapse_sdk.testing — convenience re-exports for test/CI usage (§2.2.4)."""

from synapse_sdk.validator import (
    AdapterValidationError,
    AdapterValidationResult,
    AdapterValidator,
    Severity,
    ValidationFailure,
)

__all__ = [
    "AdapterValidationError",
    "AdapterValidationResult",
    "AdapterValidator",
    "Severity",
    "ValidationFailure",
]
