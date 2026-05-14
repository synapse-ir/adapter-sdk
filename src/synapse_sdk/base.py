# SPDX-FileCopyrightText: 2024 Chris Widmer
# SPDX-License-Identifier: MIT
"""AdapterBase — abstract base class for all SYNAPSE adapters (§2.1, §2.2)."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

from synapse_sdk.types import CanonicalIR, ProvenanceEntry


class AdapterConfigurationError(ValueError):
    """Raised when build_provenance receives invalid arguments (G-C06 envelope)."""

    def __init__(self, field: str, reason: str, expected: Any, received: Any) -> None:
        self.envelope: dict[str, Any] = {
            "error": "ADAPTER_CONFIGURATION_ERROR",
            "message": (
                f"build_provenance() argument '{field}' is invalid: {reason}. "
                f"Expected {expected}, received {received!r}."
            ),
            "field": field,
            "expected": expected,
            "received": received,
            "recommendation": (
                f"Pass a value for '{field}' that satisfies: {expected}."
            ),
        }
        super().__init__(json.dumps(self.envelope))


class AdapterBase(ABC):
    """
    Abstract base for SYNAPSE adapters.

    Subclasses must declare MODEL_ID and ADAPTER_VERSION as class-level strings
    and implement ingress() and egress().  All methods must be pure — no network
    calls, no persistent state, no side effects.
    """

    # ------------------------------------------------------------------
    # Abstract class attributes — subclasses MUST set these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def MODEL_ID(self) -> str:  # noqa: N802  (spec mandates this casing)
        """Identifier that MUST match the model's registry entry."""

    @property
    @abstractmethod
    def ADAPTER_VERSION(self) -> str:  # noqa: N802
        """Semver string bumped when adapter logic changes."""

    # ------------------------------------------------------------------
    # Abstract transform methods
    # ------------------------------------------------------------------

    @abstractmethod
    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        """
        Convert canonical IR into the model's native input format.

        Contract:
        - MUST be pure — no network calls, no side effects.
        - MUST NOT raise on valid IR — return best-effort transformation.
        - MUST NOT return None.
        """

    @abstractmethod
    def egress(
        self,
        model_output: dict[str, Any],
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        """
        Convert model output back to canonical IR.

        Contract:
        - MUST return a valid CanonicalIR.
        - MUST append exactly one ProvenanceEntry (use build_provenance).
        - MUST NOT modify any existing ProvenanceEntry.
        - MUST carry forward task_header and compliance_envelope unchanged.
        """

    # ------------------------------------------------------------------
    # Concrete helper
    # ------------------------------------------------------------------

    def build_provenance(
        self,
        confidence: float,
        latency_ms: int,
        *,
        cost_usd: float | None = None,
        token_count: int | None = None,
        warnings: list[str] | None = None,
        timestamp_unix: int | None = None,
    ) -> ProvenanceEntry:
        """
        Construct a ProvenanceEntry pre-filled with this adapter's identity.

        Raises AdapterConfigurationError (G-C06 envelope) when:
        - confidence is outside [0.0, 1.0]
        - latency_ms is negative
        - cost_usd is negative
        """
        if not (0.0 <= confidence <= 1.0):
            raise AdapterConfigurationError(
                field="confidence",
                reason="confidence must be a float in [0.0, 1.0]",
                expected="float in range [0.0, 1.0]",
                received=confidence,
            )
        if latency_ms < 0:
            raise AdapterConfigurationError(
                field="latency_ms",
                reason="latency_ms must be a non-negative integer",
                expected="integer >= 0",
                received=latency_ms,
            )
        if cost_usd is not None and cost_usd < 0.0:
            raise AdapterConfigurationError(
                field="cost_usd",
                reason="cost_usd must be non-negative when provided",
                expected="float >= 0.0 or None",
                received=cost_usd,
            )

        return ProvenanceEntry(
            model_id=self.MODEL_ID,
            adapter_version=self.ADAPTER_VERSION,
            confidence=confidence,
            latency_ms=latency_ms,
            timestamp_unix=timestamp_unix if timestamp_unix is not None else int(time.time()),
            cost_usd=cost_usd,
            token_count=token_count,
            warnings=warnings,
        )
