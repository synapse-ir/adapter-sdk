"""Tests for G-S01 — Distributed Tracing (tracing.py + TraceContext schema)."""

from __future__ import annotations

import re

import pytest

from synapse_sdk.tracing import (
    _build_traceparent,
    _new_span_id,
    _new_trace_id,
    make_child_traceparent,
    propagate_trace_context,
)
from synapse_sdk.types import (
    CanonicalIR,
    Domain,
    Payload,
    TaskHeader,
    TaskType,
    TraceContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
_TRACE_ID          = "4bf92f3577b34da6a3ce929d0e0e4736"
_TRACEPARENT_RE    = re.compile(
    r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
)


def _make_ir(*, trace_context: TraceContext | None = None) -> CanonicalIR:
    return CanonicalIR(
        ir_version="1.0.0",
        message_id="00000000-0000-4000-8000-000000000001",
        task_header=TaskHeader(
            task_type=TaskType.extract,
            domain=Domain.legal,
            priority=2,
            latency_budget_ms=500,
            trace_context=trace_context,
        ),
        payload=Payload(modality="text", content="hello"),
    )


# ---------------------------------------------------------------------------
# TraceContext schema validation
# ---------------------------------------------------------------------------

class TestTraceContextSchema:
    def test_valid_traceparent_accepted(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        assert tc.traceparent == _VALID_TRACEPARENT

    def test_traceparent_normalised_to_lowercase(self):
        upper = "00-4BF92F3577B34DA6A3CE929D0E0E4736-00F067AA0BA902B7-01"
        tc = TraceContext(traceparent=upper)
        assert tc.traceparent == upper.lower()

    def test_tracestate_optional(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        assert tc.tracestate is None

    def test_tracestate_accepted(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT, tracestate="vendor=value")
        assert tc.tracestate == "vendor=value"

    def test_invalid_traceparent_short_trace_id(self):
        with pytest.raises(Exception):
            TraceContext(traceparent="00-4bf92f35-00f067aa0ba902b7-01")

    def test_invalid_traceparent_no_dashes(self):
        with pytest.raises(Exception):
            TraceContext(traceparent="004bf92f3577b34da6a3ce929d0e0e473600f067aa0ba902b701")

    def test_null_byte_in_traceparent_rejected(self):
        bad = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba9\x0002b7-01"
        with pytest.raises(Exception):
            TraceContext(traceparent=bad)

    def test_null_byte_in_tracestate_rejected(self):
        with pytest.raises(Exception):
            TraceContext(traceparent=_VALID_TRACEPARENT, tracestate="vendor\x00=bad")

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            TraceContext(traceparent=_VALID_TRACEPARENT, unknown_field="x")

    def test_round_trip_json(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT, tracestate="k=v")
        ir = _make_ir(trace_context=tc)
        ir2 = CanonicalIR.from_json(ir.to_json())
        assert ir2.task_header.trace_context is not None
        assert ir2.task_header.trace_context.traceparent == _VALID_TRACEPARENT
        assert ir2.task_header.trace_context.tracestate == "k=v"


# ---------------------------------------------------------------------------
# TaskHeader trace_context field
# ---------------------------------------------------------------------------

class TestTaskHeaderTraceContext:
    def test_trace_context_absent_by_default(self):
        th = TaskHeader(
            task_type=TaskType.classify,
            domain=Domain.general,
            priority=1,
            latency_budget_ms=100,
        )
        assert th.trace_context is None

    def test_trace_context_accepted(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        th = TaskHeader(
            task_type=TaskType.classify,
            domain=Domain.general,
            priority=1,
            latency_budget_ms=100,
            trace_context=tc,
        )
        assert th.trace_context == tc

    def test_ir_without_trace_context_valid(self):
        ir = _make_ir(trace_context=None)
        assert ir.task_header.trace_context is None

    def test_ir_with_trace_context_valid(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        ir = _make_ir(trace_context=tc)
        assert ir.task_header.trace_context.traceparent == _VALID_TRACEPARENT


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    def test_new_trace_id_length(self):
        tid = _new_trace_id()
        assert len(tid) == 32
        assert re.fullmatch(r"[0-9a-f]+", tid)

    def test_new_span_id_length(self):
        sid = _new_span_id()
        assert len(sid) == 16
        assert re.fullmatch(r"[0-9a-f]+", sid)

    def test_build_traceparent_format(self):
        tp = _build_traceparent("a" * 32, "b" * 16, "01")
        assert _TRACEPARENT_RE.match(tp)

    def test_new_trace_ids_unique(self):
        assert _new_trace_id() != _new_trace_id()

    def test_new_span_ids_unique(self):
        assert _new_span_id() != _new_span_id()


# ---------------------------------------------------------------------------
# make_child_traceparent
# ---------------------------------------------------------------------------

class TestMakeChildTraceparent:
    def test_same_trace_id(self):
        child = make_child_traceparent(_VALID_TRACEPARENT)
        _, child_trace_id, _, _ = child.split("-")
        assert child_trace_id == _TRACE_ID

    def test_different_span_id(self):
        child = make_child_traceparent(_VALID_TRACEPARENT)
        _, _, child_span_id, _ = child.split("-")
        assert child_span_id != "00f067aa0ba902b7"

    def test_flags_preserved(self):
        # flags byte "00" (not sampled) should propagate
        unsampled = f"00-{_TRACE_ID}-00f067aa0ba902b7-00"
        child = make_child_traceparent(unsampled)
        assert child.endswith("-00")

    def test_output_valid_w3c_format(self):
        child = make_child_traceparent(_VALID_TRACEPARENT)
        assert _TRACEPARENT_RE.match(child), f"Invalid traceparent: {child!r}"

    def test_chained_calls_unique_spans(self):
        c1 = make_child_traceparent(_VALID_TRACEPARENT)
        c2 = make_child_traceparent(_VALID_TRACEPARENT)
        assert c1 != c2


# ---------------------------------------------------------------------------
# propagate_trace_context
# ---------------------------------------------------------------------------

class TestPropagateTraceContext:
    def test_with_existing_trace_context_preserves_trace_id(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        ir = _make_ir(trace_context=tc)

        result = propagate_trace_context(ir)

        _, result_trace_id, _, _ = result.traceparent.split("-")
        assert result_trace_id == _TRACE_ID

    def test_with_existing_trace_context_new_span_id(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        ir = _make_ir(trace_context=tc)

        result = propagate_trace_context(ir)

        _, _, original_span, _ = _VALID_TRACEPARENT.split("-")
        _, _, result_span, _   = result.traceparent.split("-")
        assert result_span != original_span

    def test_with_existing_trace_context_preserves_tracestate(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT, tracestate="rojo=00f067")
        ir = _make_ir(trace_context=tc)

        result = propagate_trace_context(ir)

        assert result.tracestate == "rojo=00f067"

    def test_without_trace_context_creates_root(self):
        ir = _make_ir(trace_context=None)
        result = propagate_trace_context(ir)

        assert _TRACEPARENT_RE.match(result.traceparent)

    def test_without_trace_context_new_trace_id(self):
        ir = _make_ir(trace_context=None)
        result = propagate_trace_context(ir)

        _, root_trace_id, _, _ = result.traceparent.split("-")
        assert root_trace_id != _TRACE_ID  # statistically always true

    def test_without_trace_context_tracestate_is_none(self):
        ir = _make_ir(trace_context=None)
        result = propagate_trace_context(ir)
        assert result.tracestate is None

    def test_result_is_valid_trace_context(self):
        ir = _make_ir(trace_context=None)
        result = propagate_trace_context(ir)
        # Should not raise
        tc = TraceContext(traceparent=result.traceparent)
        assert tc is not None

    def test_does_not_mutate_incoming_ir(self):
        tc = TraceContext(traceparent=_VALID_TRACEPARENT)
        ir = _make_ir(trace_context=tc)
        original_traceparent = ir.task_header.trace_context.traceparent

        propagate_trace_context(ir)

        assert ir.task_header.trace_context.traceparent == original_traceparent

    def test_each_call_produces_unique_span(self):
        ir = _make_ir(trace_context=None)
        r1 = propagate_trace_context(ir)
        r2 = propagate_trace_context(ir)
        assert r1.traceparent != r2.traceparent


# ---------------------------------------------------------------------------
# adapter_span — OTel disabled (default)
# ---------------------------------------------------------------------------

class TestAdapterSpanOtelDisabled:
    """With SYNAPSE_OTEL_ENABLED=false (default) adapter_span is a no-op."""

    def test_yields_none_when_otel_disabled(self):
        from synapse_sdk.tracing import adapter_span

        ir = _make_ir()
        with adapter_span(ir, "test-model", "1.0.0", "ingress") as span:
            assert span is None

    def test_does_not_raise_on_egress(self):
        from synapse_sdk.tracing import adapter_span

        ir = _make_ir()
        with adapter_span(
            ir, "test-model", "1.0.0", "egress",
            latency_ms=42, confidence=0.95
        ) as span:
            assert span is None

    def test_context_manager_cleans_up(self):
        from synapse_sdk.tracing import adapter_span

        ir = _make_ir()
        entered = False
        with adapter_span(ir, "m", "1.0.0", "ingress") as span:
            entered = True
            _ = span
        assert entered


# ---------------------------------------------------------------------------
# _get_otel_tracer — OTel enabled but opentelemetry not installed
# ---------------------------------------------------------------------------

class TestGetOtelTracer:
    """Exercise _get_otel_tracer() import-error and cache branches."""

    def _reset(self, monkeypatch):
        import synapse_sdk.tracing as mod
        monkeypatch.setattr(mod, "_OTEL_ENABLED", True)
        monkeypatch.setattr(mod, "_otel_tracer", None)
        monkeypatch.setattr(mod, "_otel_import_attempted", False)
        return mod

    def test_import_error_returns_none(self, monkeypatch):
        mod = self._reset(monkeypatch)
        result = mod._get_otel_tracer()
        assert result is None
        assert mod._otel_import_attempted is True

    def test_already_attempted_returns_none_without_retry(self, monkeypatch):
        mod = self._reset(monkeypatch)
        mod._get_otel_tracer()          # first call sets _otel_import_attempted
        result = mod._get_otel_tracer() # second call — fast-path return
        assert result is None

    def test_cached_tracer_returned_immediately(self, monkeypatch):
        import synapse_sdk.tracing as mod
        sentinel = object()
        monkeypatch.setattr(mod, "_OTEL_ENABLED", True)
        monkeypatch.setattr(mod, "_otel_tracer", sentinel)
        assert mod._get_otel_tracer() is sentinel


# ---------------------------------------------------------------------------
# adapter_span — OTel enabled, opentelemetry mocked
# ---------------------------------------------------------------------------

class TestAdapterSpanOtelEnabled:
    """Exercise the OTel code paths inside adapter_span()."""

    def test_yields_none_when_import_fails_inside_span(self, monkeypatch):
        """_get_otel_tracer returns a mock but opentelemetry is not installed —
        the inner import raises ModuleNotFoundError caught by except Exception."""
        import synapse_sdk.tracing as mod
        monkeypatch.setattr(mod, "_get_otel_tracer", lambda: object())

        ir = _make_ir()
        with mod.adapter_span(ir, "m", "1.0.0", "ingress") as span:
            assert span is None

    def test_yields_span_with_mocked_otel(self, monkeypatch):
        """Happy path: tracer and propagator both mocked."""
        import sys
        from unittest.mock import MagicMock
        import synapse_sdk.tracing as mod

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_span)
        cm.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = cm

        monkeypatch.setattr(mod, "_get_otel_tracer", lambda: mock_tracer)

        mock_propagator = MagicMock()
        mock_propagator.return_value.extract.return_value = {}
        otel_mod = MagicMock()
        otel_mod.TraceContextTextMapPropagator = mock_propagator

        with monkeypatch.context() as m:
            m.setitem(sys.modules, "opentelemetry", MagicMock())
            m.setitem(sys.modules, "opentelemetry.trace", MagicMock())
            m.setitem(sys.modules, "opentelemetry.trace.propagation", MagicMock())
            m.setitem(
                sys.modules,
                "opentelemetry.trace.propagation.tracecontext",
                otel_mod,
            )
            ir = _make_ir()
            with mod.adapter_span(ir, "m", "1.0.0", "egress", latency_ms=42, confidence=0.9) as span:
                assert span is mock_span

    def test_yields_span_with_trace_context(self, monkeypatch):
        """Covers the branch where ir.task_header.trace_context is not None."""
        import sys
        from unittest.mock import MagicMock
        import synapse_sdk.tracing as mod

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_span)
        cm.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = cm

        monkeypatch.setattr(mod, "_get_otel_tracer", lambda: mock_tracer)

        mock_propagator = MagicMock()
        mock_propagator.return_value.extract.return_value = {}
        otel_mod = MagicMock()
        otel_mod.TraceContextTextMapPropagator = mock_propagator

        tc = TraceContext(
            traceparent=_VALID_TRACEPARENT,
            tracestate="vendor=abc",
        )
        ir = _make_ir(trace_context=tc)

        with monkeypatch.context() as m:
            m.setitem(sys.modules, "opentelemetry", MagicMock())
            m.setitem(sys.modules, "opentelemetry.trace", MagicMock())
            m.setitem(sys.modules, "opentelemetry.trace.propagation", MagicMock())
            m.setitem(
                sys.modules,
                "opentelemetry.trace.propagation.tracecontext",
                otel_mod,
            )
            with mod.adapter_span(ir, "m", "1.0.0", "ingress") as span:
                assert span is mock_span
