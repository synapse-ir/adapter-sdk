# SPDX-FileCopyrightText: 2024 Chris Widmer
# SPDX-License-Identifier: MIT
"""AdapterValidator — runs all 13 §2.4 validation rules against an adapter."""

from __future__ import annotations

import ast
import inspect
import json
import re
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from synapse_sdk.types import (
    CanonicalIR,
    Domain,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
)

if TYPE_CHECKING:
    from synapse_sdk.base import AdapterBase


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class Severity(StrEnum):
    MUST   = "MUST"    # hard failure — adapter is rejected
    SHOULD = "SHOULD"  # warning — published with advisory


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ValidationFailure:
    rule_id:  str
    message:  str
    severity: Severity

    def to_envelope(self) -> dict[str, Any]:
        """G-C06 envelope for this failure."""
        return {
            "error": "ADAPTER_VALIDATION_FAILED",
            "message": f"[{self.rule_id}] {self.message}",
            "rule_id": self.rule_id,
            "severity": str(self.severity),
            "recommendation": _RULE_RECOMMENDATIONS.get(self.rule_id, "See §2.4 of the spec."),
        }


@dataclass
class AdapterValidationResult:
    passed:   bool
    errors:   list[ValidationFailure] = field(default_factory=list)
    warnings: list[ValidationFailure] = field(default_factory=list)

    def summary(self) -> str:
        lines: list[str] = []
        status = "PASSED" if self.passed else "FAILED"
        lines.append(f"Validation {status} — {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        for f_ in self.errors:
            lines.append(f"  [ERROR]   [{f_.rule_id}] {f_.message}")
        for f_ in self.warnings:
            lines.append(f"  [WARNING] [{f_.rule_id}] {f_.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class AdapterValidationError(Exception):
    """Raised by assert_valid() when one or more MUST rules fail (G-C06)."""

    def __init__(self, result: AdapterValidationResult) -> None:
        self.result = result
        envelope = {
            "error": "ADAPTER_VALIDATION_FAILED",
            "message": (
                f"Adapter failed {len(result.errors)} validation rule(s). "
                "Fix all MUST-level errors before publishing."
            ),
            "failures": [e.to_envelope() for e in result.errors],
            "warnings": [w.to_envelope() for w in result.warnings],
            "request_id": str(uuid.uuid4()),
            "timestamp_unix": int(time.time()),
        }
        super().__init__(json.dumps(envelope, indent=2))


# ---------------------------------------------------------------------------
# Per-rule fix recommendations (G-C06)
# ---------------------------------------------------------------------------

_RULE_RECOMMENDATIONS: dict[str, str] = {
    "INGRESS_NOT_NULL":    "Return a dict (even empty {}) from ingress(), never None.",
    "EGRESS_RETURNS_IR":   "Return a valid CanonicalIR from egress(). Use original_ir.clone() as a starting point.",
    "PROVENANCE_APPENDED": "Call updated.provenance.append(self.build_provenance(...)) exactly once inside egress().",
    "PROVENANCE_IMMUTABLE":"Do not mutate existing ProvenanceEntry objects. Only append new entries.",
    "TASK_HEADER_CARRIED": "Assign original_ir.task_header to the returned IR unchanged — do not reconstruct it.",
    "COMPLIANCE_CARRIED":  "Assign original_ir.compliance_envelope to the returned IR unchanged.",
    "NO_NETWORK_CALLS":    "Remove all network I/O from ingress/egress. Adapters must be pure transforms.",
    "CONFIDENCE_RANGE":    "Pass a float in [0.0, 1.0] as confidence to build_provenance().",
    "MODEL_ID_MATCH":      "Set ProvenanceEntry.model_id = self.MODEL_ID, or use build_provenance().",
    "VERSION_SEMVER":      "Set ADAPTER_VERSION to a valid semver string, e.g. '1.0.0'.",
    "LATENCY_POSITIVE":    "Pass latency_ms > 0 to build_provenance(). Use actual wall-clock latency.",
    "COST_NON_NEGATIVE":   "Pass cost_usd >= 0.0 (or omit it) in build_provenance().",
    "CONTENT_PRESERVED":   "Do not overwrite payload.content in egress(). Mutate payload fields only as needed.",
}

# ---------------------------------------------------------------------------
# Network-call AST scanner (NO_NETWORK_CALLS rule)
# ---------------------------------------------------------------------------

_NETWORK_MODULES = frozenset({
    "requests", "httpx", "urllib", "urllib2", "urllib3",
    "socket", "aiohttp", "http", "ftplib", "smtplib",
})

# Attribute access patterns like requests.get, socket.connect, httpx.AsyncClient
_NETWORK_ATTR_PREFIXES = frozenset({
    "requests", "httpx", "urllib", "socket", "aiohttp",
})


def _find_network_calls(fn: Any) -> list[str]:
    """Return list of human-readable descriptions of network calls found via AST scan."""
    try:
        src = inspect.getsource(fn)
        src = textwrap.dedent(src)
        tree = ast.parse(src)
    except (OSError, TypeError, IndentationError):
        return []

    findings: list[str] = []

    for node in ast.walk(tree):
        # import requests  /  import socket
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _NETWORK_MODULES:
                    findings.append(f"import {alias.name}")

        # from requests import get  /  from urllib.request import urlopen
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root in _NETWORK_MODULES:
                names = ", ".join(a.name for a in node.names)
                findings.append(f"from {module} import {names}")

        # requests.get(...)  /  socket.connect(...)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id in _NETWORK_ATTR_PREFIXES
                ):
                    findings.append(f"{node.func.value.id}.{node.func.attr}()")

    return findings


# ---------------------------------------------------------------------------
# Minimal fixture factory
# ---------------------------------------------------------------------------

_FIXTURE_CONTENT = "The court held that the defendant was liable."


def _minimal_ir() -> CanonicalIR:
    return CanonicalIR(
        ir_version="1.0.0",
        message_id=str(uuid.uuid4()),
        task_header=TaskHeader(
            task_type=TaskType.extract,
            domain=Domain.legal,
            priority=2,
            latency_budget_ms=500,
        ),
        payload=Payload(
            modality="text",
            content=_FIXTURE_CONTENT,
        ),
    )


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class AdapterValidator:
    """
    Runs the full §2.4 validation suite against an AdapterBase instance.

    Usage::

        validator = AdapterValidator(MyAdapter())
        result = validator.run()
        validator.assert_valid()   # raises AdapterValidationError if MUST rules fail

    Pass a fixture list to run behavioral rules against multiple IRs::

        from synapse_sdk.testing.fixtures import ALL_FIXTURES
        validator = AdapterValidator(MyAdapter(), fixtures=ALL_FIXTURES)
        result = validator.run()
    """

    def __init__(
        self,
        adapter: AdapterBase,
        fixtures: list[CanonicalIR] | None = None,
    ) -> None:
        self._adapter = adapter
        self._fixtures: list[CanonicalIR] = fixtures if fixtures is not None else []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> AdapterValidationResult:
        """Execute all 13 rules and return a consolidated result.

        Behavioral rules (1–6, 8–9, 11–13) run once per fixture; static rules
        (7, 10) run once regardless of fixture count.  When no fixtures were
        passed to __init__(), a single built-in minimal fixture is used.
        """
        errors:   list[ValidationFailure] = []
        warnings: list[ValidationFailure] = []

        # Static rules — independent of any fixture
        r7 = self._rule_no_network_calls()
        if r7:
            errors.append(r7)

        r10 = self._rule_version_semver()
        if r10:
            errors.append(r10)

        # Behavioural rules — run per fixture
        fixtures = self._fixtures or [_minimal_ir()]
        for fixture in fixtures:
            f_errors, f_warnings = self._run_fixture(fixture)
            errors.extend(f_errors)
            warnings.extend(f_warnings)

        passed = len(errors) == 0
        return AdapterValidationResult(passed=passed, errors=errors, warnings=warnings)

    # ------------------------------------------------------------------
    # Per-fixture behavioural runner
    # ------------------------------------------------------------------

    def _run_fixture(
        self, fixture: CanonicalIR
    ) -> tuple[list[ValidationFailure], list[ValidationFailure]]:
        """Run all behavioural rules against a single fixture IR."""
        errors:   list[ValidationFailure] = []
        warnings: list[ValidationFailure] = []

        # -- Run ingress; keep result for downstream rules ---------------
        ingress_output: Any = None
        ingress_ok = False
        try:
            ingress_output = self._adapter.ingress(fixture)
            ingress_ok = True
        except Exception as exc:
            errors.append(ValidationFailure(
                rule_id="INGRESS_NOT_NULL",
                severity=Severity.MUST,
                message=(
                    f"ingress() raised an unexpected exception: {type(exc).__name__}: {exc}. "
                    "ingress() MUST return a dict without raising on valid IR."
                ),
            ))

        # Rule 1
        _r1 = self._rule_ingress_not_null(ingress_output, ingress_ok)
        if _r1:
            errors.append(_r1)

        # -- Run egress; keep result for downstream rules ----------------
        egress_output: Any = None
        egress_ir: CanonicalIR | None = None
        egress_raised = False
        provenance_before = list(fixture.provenance)

        dummy_model_output: dict[str, Any] = {
            "result": "test",
            "model_conf": 0.9,
        }
        try:
            egress_output = self._adapter.egress(dummy_model_output, fixture, latency_ms=42)
            if isinstance(egress_output, CanonicalIR):
                egress_ir = egress_output
        except Exception as exc:
            egress_raised = True
            errors.append(ValidationFailure(
                rule_id="EGRESS_RETURNS_IR",
                severity=Severity.MUST,
                message=(
                    f"egress() raised an unexpected exception: {type(exc).__name__}: {exc}. "
                    "egress() MUST return a valid CanonicalIR without raising."
                ),
            ))

        # Rule 2 — only check if egress did not raise (raise is already recorded)
        if not egress_raised:
            for failure in self._rule_egress_returns_ir(egress_output):
                errors.append(failure)

        if egress_ir is not None:
            r3 = self._rule_provenance_appended(fixture, egress_ir)
            if r3:
                errors.append(r3)

            r4 = self._rule_provenance_immutable(provenance_before, egress_ir)
            if r4:
                errors.append(r4)

            r5 = self._rule_task_header_carried(fixture, egress_ir)
            if r5:
                errors.append(r5)

            r6 = self._rule_compliance_carried(fixture, egress_ir)
            if r6:
                errors.append(r6)

            # Inspect the new provenance entry for rules 8-12
            new_entry = self._new_provenance_entry(fixture, egress_ir)
            if new_entry is not None:
                r8 = self._rule_confidence_range(new_entry)
                if r8:
                    errors.append(r8)

                r9 = self._rule_model_id_match(new_entry)
                if r9:
                    errors.append(r9)

                r11 = self._rule_latency_positive(new_entry)
                if r11:
                    warnings.append(r11)

                r12 = self._rule_cost_non_negative(new_entry)
                if r12:
                    warnings.append(r12)

            r13 = self._rule_content_preserved(fixture, egress_ir)
            if r13:
                warnings.append(r13)

        return errors, warnings

    def assert_valid(self) -> None:
        """Run validation and raise AdapterValidationError if any MUST rule fails."""
        result = self.run()
        if not result.passed:
            raise AdapterValidationError(result)

    def assert_valid_on(self, fixture: CanonicalIR) -> None:
        """Run validation against a single fixture and raise AdapterValidationError on failure."""
        AdapterValidator(self._adapter, fixtures=[fixture]).assert_valid()

    # ------------------------------------------------------------------
    # Rule implementations (private)
    # ------------------------------------------------------------------

    def _rule_ingress_not_null(
        self, output: Any, ran_ok: bool
    ) -> ValidationFailure | None:
        """INGRESS_NOT_NULL — ingress() must never return None."""
        if not ran_ok:
            return None  # already recorded as an exception above
        if output is None:
            return ValidationFailure(
                rule_id="INGRESS_NOT_NULL",
                severity=Severity.MUST,
                message=(
                    "ingress() returned None. "
                    "ingress() MUST return a dict (even an empty {}). "
                    "Returning None will cause the orchestrator to crash."
                ),
            )
        return None

    def _rule_egress_returns_ir(self, output: Any) -> list[ValidationFailure]:
        """EGRESS_RETURNS_IR — egress() must return a valid CanonicalIR."""
        failures = []
        if output is None:
            failures.append(ValidationFailure(
                rule_id="EGRESS_RETURNS_IR",
                severity=Severity.MUST,
                message=(
                    "egress() returned None instead of a CanonicalIR. "
                    "egress() MUST always return a fully-populated CanonicalIR object."
                ),
            ))
        elif not isinstance(output, CanonicalIR):
            failures.append(ValidationFailure(
                rule_id="EGRESS_RETURNS_IR",
                severity=Severity.MUST,
                message=(
                    f"egress() returned {type(output).__name__!r} instead of CanonicalIR. "
                    "egress() MUST return a CanonicalIR. "
                    "Use original_ir.clone() or original_ir.copy() as the starting point."
                ),
            ))
        return failures

    def _rule_provenance_appended(
        self, original: CanonicalIR, result: CanonicalIR
    ) -> ValidationFailure | None:
        """PROVENANCE_APPENDED — egress() must append exactly one ProvenanceEntry."""
        before = len(original.provenance)
        after  = len(result.provenance)
        delta  = after - before
        if delta == 1:
            return None
        if delta == 0:
            return ValidationFailure(
                rule_id="PROVENANCE_APPENDED",
                severity=Severity.MUST,
                message=(
                    "egress() did not append a ProvenanceEntry — provenance length unchanged. "
                    "egress() MUST call updated.provenance.append(self.build_provenance(...)) "
                    "exactly once before returning."
                ),
            )
        return ValidationFailure(
            rule_id="PROVENANCE_APPENDED",
            severity=Severity.MUST,
            message=(
                f"egress() appended {delta} ProvenanceEntry object(s); expected exactly 1. "
                "Call build_provenance() once and append the result."
            ),
        )

    def _rule_provenance_immutable(
        self, before: list[ProvenanceEntry], result: CanonicalIR
    ) -> ValidationFailure | None:
        """PROVENANCE_IMMUTABLE — existing ProvenanceEntry objects must not be mutated."""
        for i, orig in enumerate(before):
            if i >= len(result.provenance):
                return ValidationFailure(
                    rule_id="PROVENANCE_IMMUTABLE",
                    severity=Severity.MUST,
                    message=(
                        f"egress() removed provenance[{i}] — provenance list shrunk. "
                        "Existing ProvenanceEntry objects MUST NOT be removed or replaced."
                    ),
                )
            current = result.provenance[i]
            orig_data    = orig.model_dump()
            current_data = current.model_dump()
            diffs = {
                k: (orig_data[k], current_data[k])
                for k in orig_data
                if orig_data[k] != current_data[k]
            }
            if diffs:
                first_key = next(iter(diffs))
                old_val, new_val = diffs[first_key]
                return ValidationFailure(
                    rule_id="PROVENANCE_IMMUTABLE",
                    severity=Severity.MUST,
                    message=(
                        f"egress() modified provenance[{i}].{first_key} "
                        f"from {old_val!r} to {new_val!r}. "
                        "Existing ProvenanceEntry objects MUST NOT be modified. "
                        "Only append new entries via updated.provenance.append(build_provenance(...))."
                    ),
                )
        return None

    def _rule_task_header_carried(
        self, original: CanonicalIR, result: CanonicalIR
    ) -> ValidationFailure | None:
        """TASK_HEADER_CARRIED — task_header must equal the original."""
        orig_dump   = original.task_header.model_dump()
        result_dump = result.task_header.model_dump()
        if orig_dump != result_dump:
            diffs = {k: (orig_dump[k], result_dump[k]) for k in orig_dump if orig_dump[k] != result_dump[k]}
            diff_str = "; ".join(f"{k}: {o!r} → {n!r}" for k, (o, n) in diffs.items())
            return ValidationFailure(
                rule_id="TASK_HEADER_CARRIED",
                severity=Severity.MUST,
                message=(
                    f"egress() mutated task_header ({diff_str}). "
                    "task_header MUST be carried forward unchanged. "
                    "Assign original_ir.task_header directly — do not reconstruct it."
                ),
            )
        return None

    def _rule_compliance_carried(
        self, original: CanonicalIR, result: CanonicalIR
    ) -> ValidationFailure | None:
        """COMPLIANCE_CARRIED — compliance_envelope must equal the original."""
        orig_dump   = original.compliance_envelope.model_dump()
        result_dump = result.compliance_envelope.model_dump()
        if orig_dump != result_dump:
            diffs = {k: (orig_dump[k], result_dump[k]) for k in orig_dump if orig_dump[k] != result_dump[k]}
            diff_str = "; ".join(f"{k}: {o!r} → {n!r}" for k, (o, n) in diffs.items())
            return ValidationFailure(
                rule_id="COMPLIANCE_CARRIED",
                severity=Severity.MUST,
                message=(
                    f"egress() mutated compliance_envelope ({diff_str}). "
                    "compliance_envelope MUST be carried forward unchanged. "
                    "Assign original_ir.compliance_envelope directly."
                ),
            )
        return None

    def _rule_no_network_calls(self) -> ValidationFailure | None:
        """NO_NETWORK_CALLS — ingress and egress must be pure; no I/O allowed."""
        findings: list[str] = []
        for method_name in ("ingress", "egress"):
            method = getattr(type(self._adapter), method_name, None)
            if method is None:
                continue
            hits = _find_network_calls(method)
            for hit in hits:
                findings.append(f"{method_name}(): {hit}")

        if not findings:
            return None

        found_str = "; ".join(findings)
        return ValidationFailure(
            rule_id="NO_NETWORK_CALLS",
            severity=Severity.MUST,
            message=(
                f"Network I/O detected in adapter source: [{found_str}]. "
                "Adapter functions MUST be pure transforms — no network calls, "
                "no file I/O, no side effects. "
                "Move I/O to the calling service; pass pre-fetched data via the IR."
            ),
        )

    def _rule_confidence_range(
        self, entry: ProvenanceEntry
    ) -> ValidationFailure | None:
        """CONFIDENCE_RANGE — ProvenanceEntry.confidence must be in [0.0, 1.0]."""
        c = entry.confidence
        if not (0.0 <= c <= 1.0):
            return ValidationFailure(
                rule_id="CONFIDENCE_RANGE",
                severity=Severity.MUST,
                message=(
                    f"ProvenanceEntry.confidence is {c!r}, which is outside [0.0, 1.0]. "
                    "confidence MUST be a float in [0.0, 1.0]. "
                    "Use build_provenance() to construct the entry — it validates this automatically."
                ),
            )
        return None

    def _rule_model_id_match(
        self, entry: ProvenanceEntry
    ) -> ValidationFailure | None:
        """MODEL_ID_MATCH — ProvenanceEntry.model_id must match adapter.MODEL_ID."""
        expected = self._adapter.MODEL_ID
        received = entry.model_id
        if received != expected:
            return ValidationFailure(
                rule_id="MODEL_ID_MATCH",
                severity=Severity.MUST,
                message=(
                    f"ProvenanceEntry.model_id is {received!r} but adapter.MODEL_ID is {expected!r}. "
                    "model_id MUST match the adapter's registered MODEL_ID exactly. "
                    "Use self.build_provenance() which sets model_id = self.MODEL_ID automatically."
                ),
            )
        return None

    def _rule_version_semver(self) -> ValidationFailure | None:
        """VERSION_SEMVER — ADAPTER_VERSION must be valid semver (X.Y.Z)."""
        ver = self._adapter.ADAPTER_VERSION
        if not _SEMVER_RE.match(ver):
            return ValidationFailure(
                rule_id="VERSION_SEMVER",
                severity=Severity.MUST,
                message=(
                    f"ADAPTER_VERSION is {ver!r}, which is not valid semver. "
                    "ADAPTER_VERSION MUST be a 'MAJOR.MINOR.PATCH' string (e.g. '1.0.0'). "
                    "Pre-release suffixes (-alpha.1) are not permitted by this validator."
                ),
            )
        return None

    def _rule_latency_positive(
        self, entry: ProvenanceEntry
    ) -> ValidationFailure | None:
        """LATENCY_POSITIVE (SHOULD) — latency_ms should be > 0."""
        if entry.latency_ms <= 0:
            return ValidationFailure(
                rule_id="LATENCY_POSITIVE",
                severity=Severity.SHOULD,
                message=(
                    f"ProvenanceEntry.latency_ms is {entry.latency_ms}. "
                    "latency_ms SHOULD be > 0 to reflect actual processing time. "
                    "Measure wall-clock time around the model call and pass it to build_provenance()."
                ),
            )
        return None

    def _rule_cost_non_negative(
        self, entry: ProvenanceEntry
    ) -> ValidationFailure | None:
        """COST_NON_NEGATIVE (SHOULD) — cost_usd, if present, should be >= 0.0."""
        if entry.cost_usd is not None and entry.cost_usd < 0.0:
            return ValidationFailure(
                rule_id="COST_NON_NEGATIVE",
                severity=Severity.SHOULD,
                message=(
                    f"ProvenanceEntry.cost_usd is {entry.cost_usd!r}, which is negative. "
                    "cost_usd SHOULD be >= 0.0 when provided. "
                    "Pass None if cost is unknown rather than a negative sentinel."
                ),
            )
        return None

    def _rule_content_preserved(
        self, original: CanonicalIR, result: CanonicalIR
    ) -> ValidationFailure | None:
        """CONTENT_PRESERVED (SHOULD) — payload.content should not be mutated by egress."""
        orig_content   = original.payload.content
        result_content = result.payload.content
        if orig_content is not None and result_content != orig_content:
            snip = repr(result_content[:80] + "…" if result_content and len(result_content) > 80 else result_content)
            return ValidationFailure(
                rule_id="CONTENT_PRESERVED",
                severity=Severity.SHOULD,
                message=(
                    f"egress() changed payload.content (was {orig_content[:40]!r}…, now {snip}). "
                    "payload.content SHOULD not be overwritten by egress(). "
                    "Populate payload.entities or use a structured modality for model results."
                ),
            )
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_provenance_entry(
        self, original: CanonicalIR, result: CanonicalIR
    ) -> ProvenanceEntry | None:
        """Return the entry appended by egress(), or None if none was added."""
        before = len(original.provenance)
        after  = len(result.provenance)
        if after > before:
            return result.provenance[before]
        return None
