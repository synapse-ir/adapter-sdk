"""G-S01 Distributed Tracing — W3C Trace Context propagation + optional OTel spans.

Design goals
------------
* Zero overhead by default: SYNAPSE_OTEL_ENABLED=false (the default) means all
  OTel code paths are skipped at the first ``if`` check — no imports, no objects.
* Opt-in OTel: set SYNAPSE_OTEL_ENABLED=true and install opentelemetry-sdk.
  If the package is absent the SDK logs a debug message and falls back silently.
* Pure W3C propagation helpers (propagate_trace_context, make_child_traceparent)
  work without any OTel dependency at all.

W3C Trace Context format (RFC)
-------------------------------
  traceparent = 00-{trace_id:32hex}-{parent_id:16hex}-{flags:2hex}
  e.g.          00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

Propagation rules (§9 G-S01)
------------------------------
1. Incoming IR has trace_context  → create child span (same trace_id, new span_id).
2. Incoming IR has no trace_context → create a new root trace.
3. Egress IR MUST carry the updated traceparent (new span_id) in trace_context.
4. OTel span name: ``synapse.adapter.{model_id}.{ingress|egress}``
5. OTel span attributes: model_id, adapter_version, task_type, domain,
   latency_ms (egress only), confidence (egress only).
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse_sdk.types import CanonicalIR, TraceContext

logger = logging.getLogger(__name__)

# Evaluated once at import time; restart required to toggle.
_OTEL_ENABLED: bool = os.getenv("SYNAPSE_OTEL_ENABLED", "false").lower() == "true"

# Cached tracer object — None until first successful OTel import.
_otel_tracer: object = None
_otel_import_attempted: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _new_trace_id() -> str:
    """Generate a 128-bit random trace ID (32 lower-hex chars)."""
    return secrets.token_hex(16)


def _new_span_id() -> str:
    """Generate a 64-bit random span ID (16 lower-hex chars)."""
    return secrets.token_hex(8)


def _parse_traceparent(traceparent: str) -> tuple[str, str, str]:
    """Return (trace_id, parent_id, flags) from a validated traceparent."""
    parts = traceparent.split("-")
    return parts[1], parts[2], parts[3]


def _build_traceparent(trace_id: str, span_id: str, flags: str = "01") -> str:
    return f"00-{trace_id}-{span_id}-{flags}"


def _get_otel_tracer() -> object:
    """Return an OTel tracer if OTel is enabled and available, else None."""
    global _otel_tracer, _otel_import_attempted
    if not _OTEL_ENABLED:
        return None
    if _otel_tracer is not None:
        return _otel_tracer
    if _otel_import_attempted:
        return None  # already failed once — don't retry on every call
    _otel_import_attempted = True
    try:
        from opentelemetry import trace
        _otel_tracer = trace.get_tracer("synapse.sdk", "0.1.0")
        logger.debug("OTel tracer initialised for synapse.sdk")
        return _otel_tracer
    except ImportError:
        logger.debug(
            "SYNAPSE_OTEL_ENABLED=true but opentelemetry-sdk is not installed; "
            "OTel spans disabled"
        )
        return None


# ---------------------------------------------------------------------------
# Public API — pure W3C propagation (no OTel dependency)
# ---------------------------------------------------------------------------

def make_child_traceparent(parent_traceparent: str) -> str:
    """Create a child traceparent from a parent, keeping the same trace_id.

    The new span ID is randomly generated. The ``flags`` byte is preserved
    from the parent (sampling decision stays the same unless explicitly changed).

    Args:
        parent_traceparent: A validated W3C traceparent string.

    Returns:
        A new traceparent string with the same trace_id but a fresh span_id.
    """
    trace_id, _parent_id, flags = _parse_traceparent(parent_traceparent)
    return _build_traceparent(trace_id, _new_span_id(), flags)


def propagate_trace_context(ir: CanonicalIR) -> TraceContext:
    """Derive the egress TraceContext for an IR hop.

    * If the IR carries a ``trace_context``: returns a child context that
      shares the same ``trace_id`` but has a fresh ``span_id``.
    * If the IR has no ``trace_context``: synthesises a new root trace
      (new trace_id + span_id, flags=01 sampled).

    This function is pure — it does not mutate the incoming IR.

    Args:
        ir: The incoming CanonicalIR being processed by an adapter hop.

    Returns:
        A new TraceContext to attach to the egress IR's task_header.
    """
    from synapse_sdk.types import TraceContext

    if ir.task_header.trace_context is not None:
        child_traceparent = make_child_traceparent(
            ir.task_header.trace_context.traceparent
        )
        return TraceContext(
            traceparent=child_traceparent,
            tracestate=ir.task_header.trace_context.tracestate,
        )

    # No incoming context — start a new root trace.
    return TraceContext(
        traceparent=_build_traceparent(_new_trace_id(), _new_span_id())
    )


# ---------------------------------------------------------------------------
# Public API — OTel instrumentation
# ---------------------------------------------------------------------------

@contextmanager
def adapter_span(
    ir: CanonicalIR,
    model_id: str,
    adapter_version: str,
    direction: str,
    *,
    latency_ms: int | None = None,
    confidence: float | None = None,
) -> Generator[object, None, None]:
    """Context manager that wraps an adapter invocation in an OTel child span.

    When ``SYNAPSE_OTEL_ENABLED=false`` (the default) or when
    ``opentelemetry-sdk`` is not installed, this is a **zero-overhead no-op**
    that immediately yields ``None``.

    Span name  : ``synapse.adapter.{model_id}.{direction}``
    Attributes : model_id, adapter_version, task_type, domain,
                 latency_ms (if provided), confidence (if provided).

    Args:
        ir:              The IR being processed (used for context extraction
                         and common attributes).
        model_id:        Adapter MODEL_ID.
        adapter_version: Adapter ADAPTER_VERSION.
        direction:       ``"ingress"`` or ``"egress"``.
        latency_ms:      Elapsed milliseconds (set on egress).
        confidence:      Result confidence score (set on egress).

    Yields:
        The active OTel Span object, or ``None`` when OTel is disabled.
    """
    tracer = _get_otel_tracer()
    if tracer is None:
        yield None
        return

    try:
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        carrier: dict[str, str] = {}
        if ir.task_header.trace_context is not None:
            carrier["traceparent"] = ir.task_header.trace_context.traceparent
            if ir.task_header.trace_context.tracestate:
                carrier["tracestate"] = ir.task_header.trace_context.tracestate

        ctx = TraceContextTextMapPropagator().extract(carrier)
        span_name = f"synapse.adapter.{model_id}.{direction}"
        attrs: dict[str, object] = {
            "synapse.model_id":        model_id,
            "synapse.adapter_version": adapter_version,
            "synapse.task_type":       str(ir.task_header.task_type),
            "synapse.domain":          str(ir.task_header.domain),
        }
        if latency_ms is not None:
            attrs["synapse.latency_ms"] = latency_ms
        if confidence is not None:
            attrs["synapse.confidence"] = confidence

        with tracer.start_as_current_span(  # type: ignore[attr-defined]
            span_name, context=ctx, attributes=attrs
        ) as span:
            yield span

    except Exception:
        # Never let OTel failures surface to the adapter pipeline.
        logger.debug("OTel span creation failed", exc_info=True)
        yield None
