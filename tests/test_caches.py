"""Tests for synapse_sdk.cache — §8 C1–C5."""

import time

import pytest

from synapse_sdk.cache import (
    AdapterInstanceCache,
    AdapterLoadError,
    CalibrationBuffer,
    CalibrationSignal,
    HeartbeatCache,
    HeartbeatResponse,
    InMemoryContextStore,
    RouteCandidate,
    RouteCacheClient,
    RouteRequest,
    RouteResponse,
    _route_cache_key,
)


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _signal(model_id: str = "m1") -> CalibrationSignal:
    return CalibrationSignal(
        model_id=model_id,
        adapter_version="1.0.0",
        task_type="classify",
        domain="general",
        latency_ms=50,
        confidence=0.9,
    )


def _route_req(**overrides) -> RouteRequest:
    return RouteRequest(
        task_type=overrides.get("task_type", "classify"),
        domain=overrides.get("domain", "legal"),
        latency_budget_ms=overrides.get("latency_budget_ms", 500),
        compliance_tags=overrides.get("compliance_tags"),
    )


def _route_resp(*model_ids: str) -> RouteResponse:
    return RouteResponse(
        candidates=[
            RouteCandidate(model_id=m, adapter_version="1.0.0", score=0.9)
            for m in model_ids
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# C1 — AdapterInstanceCache
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def clean_adapter_cache():
    """Reset AdapterInstanceCache class-level mutable state around each test."""
    AdapterInstanceCache._cache.clear()
    AdapterInstanceCache._registry.clear()
    yield
    AdapterInstanceCache._cache.clear()
    AdapterInstanceCache._registry.clear()


class TestAdapterInstanceCache:

    def test_get_raises_for_unknown_key(self, clean_adapter_cache):
        with pytest.raises(AdapterLoadError):
            AdapterInstanceCache.get("ghost-model", "9.9.9")

    def test_register_and_get_roundtrip(self, clean_adapter_cache):
        sentinel = object()
        AdapterInstanceCache.register("mdl", "1.0.0", lambda: sentinel)
        assert AdapterInstanceCache.get("mdl", "1.0.0") is sentinel

    def test_invalidate_removes_entry(self, clean_adapter_cache):
        AdapterInstanceCache.register("mdl", "1.0.0", lambda: object())
        AdapterInstanceCache.get("mdl", "1.0.0")
        assert "mdl:1.0.0" in AdapterInstanceCache._cache

        AdapterInstanceCache.invalidate("mdl", "1.0.0")
        assert "mdl:1.0.0" not in AdapterInstanceCache._cache

    def test_lru_eviction_drops_oldest_entry(self, clean_adapter_cache):
        original_max = AdapterInstanceCache._max
        AdapterInstanceCache._max = 2
        try:
            for name in ("m1", "m2", "m3"):
                AdapterInstanceCache.register(name, "1.0", lambda n=name: n)
            AdapterInstanceCache.get("m1", "1.0")
            AdapterInstanceCache.get("m2", "1.0")
            # Cache is full (2 entries). Getting m3 evicts the oldest (m1).
            AdapterInstanceCache.get("m3", "1.0")

            assert "m1:1.0" not in AdapterInstanceCache._cache
            assert "m2:1.0" in AdapterInstanceCache._cache
            assert "m3:1.0" in AdapterInstanceCache._cache
        finally:
            AdapterInstanceCache._max = original_max


# ──────────────────────────────────────────────────────────────────────────────
# C2 — RouteCacheClient
# ──────────────────────────────────────────────────────────────────────────────

class TestRouteCacheClient:

    def test_key_construction_is_deterministic(self):
        req = _route_req()
        assert _route_cache_key(req) == _route_cache_key(req)

    def test_sorted_compliance_tags_produce_same_key(self):
        req_a = _route_req(compliance_tags=["pii", "gdpr"])
        req_b = _route_req(compliance_tags=["gdpr", "pii"])
        assert _route_cache_key(req_a) == _route_cache_key(req_b)

    def test_get_returns_none_on_cache_miss(self):
        client = RouteCacheClient()
        assert client.get(_route_req(task_type="embed", domain="finance")) is None

    def test_set_and_get_roundtrip(self):
        client = RouteCacheClient()
        req = _route_req()
        resp = _route_resp("target-model")
        client.set(req, resp)
        cached = client.get(req)
        assert cached is not None
        assert cached.candidates[0].model_id == "target-model"

    def test_invalidate_model_removes_entries_containing_that_model(self):
        client = RouteCacheClient()
        req = _route_req()
        client.set(req, _route_resp("target-model", "other-model"))
        assert client.get(req) is not None

        client.invalidate_model("target-model")
        assert client.get(req) is None


# ──────────────────────────────────────────────────────────────────────────────
# C3 — HeartbeatCache
# ──────────────────────────────────────────────────────────────────────────────

class TestHeartbeatCache:

    def test_store_and_retrieve_by_model_id(self):
        cache = HeartbeatCache()
        cache.store(HeartbeatResponse(model_id="mdl", status="available", capacity_pct=0.85))
        result = cache.get("mdl")
        assert result is not None
        assert result.model_id == "mdl"
        assert result.status == "available"

    def test_is_stale_false_for_fresh_entry(self):
        cache = HeartbeatCache(stale_threshold_s=30)
        cache.store(HeartbeatResponse(model_id="fresh", status="available"))
        assert cache.is_stale("fresh") is False

    def test_is_stale_true_after_threshold_passes(self):
        cache = HeartbeatCache(stale_threshold_s=0.02)
        cache.store(HeartbeatResponse(model_id="old", status="available"))
        time.sleep(0.05)
        assert cache.is_stale("old") is True


# ──────────────────────────────────────────────────────────────────────────────
# C4 — InMemoryContextStore
# ──────────────────────────────────────────────────────────────────────────────

class TestInMemoryContextStore:

    def test_get_returns_none_for_missing_key(self):
        store = InMemoryContextStore()
        assert store.get("sess-1", "no-such-key") is None

    def test_set_and_get_roundtrip(self):
        store = InMemoryContextStore()
        store.set("sess-1", "mykey", b"hello bytes")
        assert store.get("sess-1", "mykey") == b"hello bytes"

    def test_delete_removes_key(self):
        store = InMemoryContextStore()
        store.set("sess-1", "k", b"data")
        store.delete("sess-1", "k")
        assert store.get("sess-1", "k") is None

    def test_expire_session_removes_all_keys_for_that_session(self):
        store = InMemoryContextStore()
        store.set("sess-a", "k1", b"v1")
        store.set("sess-a", "k2", b"v2")
        store.set("sess-b", "k3", b"v3")

        store.expire_session("sess-a")

        assert store.get("sess-a", "k1") is None
        assert store.get("sess-a", "k2") is None
        assert store.get("sess-b", "k3") == b"v3"  # unaffected session


# ──────────────────────────────────────────────────────────────────────────────
# C5 — CalibrationBuffer
# ──────────────────────────────────────────────────────────────────────────────

class TestCalibrationBuffer:

    def test_submit_returns_within_100ms(self):
        buf = CalibrationBuffer()
        t0 = time.monotonic()
        buf.submit(_signal())
        assert (time.monotonic() - t0) * 1000 < 100

    def test_buffer_accepts_signals_up_to_max_size(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CAL_BUFFER_MAX", "5")
        monkeypatch.setenv("SYNAPSE_CAL_FLUSH_INTERVAL_SECONDS", "3600")
        buf = CalibrationBuffer()
        for i in range(5):
            buf.submit(_signal(model_id=f"m{i}"))
        with buf._lock:
            assert len(buf._buffer) == 5

    def test_overflow_drops_oldest_not_newest(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CAL_BUFFER_MAX", "3")
        monkeypatch.setenv("SYNAPSE_CAL_FLUSH_INTERVAL_SECONDS", "3600")
        buf = CalibrationBuffer()
        for i in range(3):
            buf.submit(_signal(model_id=f"m{i}"))
        buf.submit(_signal(model_id="newest"))
        with buf._lock:
            ids = [s.model_id for s in buf._buffer]
        assert "m0" not in ids
        assert "newest" in ids

    def test_disabled_via_env_discards_signals_silently(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_CAL_ENABLED", "false")
        buf = CalibrationBuffer()
        buf.submit(_signal())
        with buf._lock:
            assert len(buf._buffer) == 0
