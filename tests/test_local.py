"""Tests for synapse_sdk.local — local development mode."""
from __future__ import annotations

import json
import os
import time
import threading

import pytest

from synapse_sdk.local import (
    CapabilityManifest,
    LocalCalibrationWriter,
    LocalManifestLoader,
    LocalRouter,
    _score_manifest,
    get_cal_writer,
    get_router,
    is_local_mode,
)
from synapse_sdk.cache import RouteRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manifest(**overrides) -> CapabilityManifest:
    defaults = dict(
        model_id="test/model",
        adapter_version="1.0.0",
        task_types=["classify"],
        domains=["general"],
        compliance_tags=[],
        latency_p50_ms=100,
        latency_p99_ms=200,
        cost_per_1k_tokens=None,
        quality_score=0.8,
        available=True,
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


def _request(**overrides) -> RouteRequest:
    defaults = dict(
        task_type="classify",
        domain="general",
        latency_budget_ms=500,
    )
    defaults.update(overrides)
    return RouteRequest(**defaults)


def _write_manifests(path, manifests: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifests, fh)


# ---------------------------------------------------------------------------
# CapabilityManifest defaults
# ---------------------------------------------------------------------------

def test_capability_manifest_defaults():
    m = CapabilityManifest(model_id="a/b", adapter_version="1.0.0")
    assert m.available is True
    assert m.quality_score == 0.8
    assert m.task_types == []
    assert m.domains == []


# ---------------------------------------------------------------------------
# _score_manifest — filtering logic
# ---------------------------------------------------------------------------

def test_score_manifest_basic():
    m = _manifest()
    score = _score_manifest(m, _request())
    assert score is not None
    assert score > 0


def test_score_manifest_unavailable_filtered():
    m = _manifest(available=False)
    assert _score_manifest(m, _request()) is None


def test_score_manifest_wrong_task_type_filtered():
    m = _manifest(task_types=["extract"])
    assert _score_manifest(m, _request(task_type="classify")) is None


def test_score_manifest_wrong_domain_filtered():
    m = _manifest(domains=["legal"])
    assert _score_manifest(m, _request(domain="medical")) is None


def test_score_manifest_missing_compliance_tag_filtered():
    m = _manifest(compliance_tags=[])
    req = _request(compliance_tags=["hipaa"])
    assert _score_manifest(m, req) is None


def test_score_manifest_has_required_compliance_tag_passes():
    m = _manifest(compliance_tags=["hipaa", "gdpr"])
    req = _request(compliance_tags=["hipaa"])
    assert _score_manifest(m, req) is not None


def test_score_manifest_cost_ceiling_filtered():
    m = _manifest(cost_per_1k_tokens=0.10)
    req = _request(cost_ceiling=0.05)
    assert _score_manifest(m, req) is None


def test_score_manifest_cost_ceiling_passes():
    m = _manifest(cost_per_1k_tokens=0.03)
    req = _request(cost_ceiling=0.05)
    assert _score_manifest(m, req) is not None


def test_score_manifest_quality_floor_filtered():
    m = _manifest(quality_score=0.6)
    req = _request(quality_floor=0.8)
    assert _score_manifest(m, req) is None


def test_score_manifest_quality_floor_passes():
    m = _manifest(quality_score=0.9)
    req = _request(quality_floor=0.8)
    assert _score_manifest(m, req) is not None


def test_score_manifest_latency_budget_filtered():
    m = _manifest(latency_p99_ms=1000)
    req = _request(latency_budget_ms=500)
    assert _score_manifest(m, req) is None


def test_score_manifest_excluded_model_filtered():
    m = _manifest(model_id="test/model")
    req = _request(exclude_models=["test/model"])
    assert _score_manifest(m, req) is None


def test_score_manifest_latency_factor_below_one():
    # p99=150 passes the budget filter (150 <= 200), but p50=300 > 200
    # so latency_factor = min(1.0, 200/300) = 0.667 — score is reduced
    m = _manifest(latency_p50_ms=300, latency_p99_ms=150)
    req = _request(latency_budget_ms=200)
    score = _score_manifest(m, req)
    assert score is not None
    assert score < m.quality_score


def test_score_manifest_zero_latency_budget():
    m = _manifest(latency_p50_ms=100, latency_p99_ms=150)
    req = _request(latency_budget_ms=0)
    score = _score_manifest(m, req)
    assert score is not None
    assert score == pytest.approx(m.quality_score)


def test_score_manifest_no_cost_ceiling_passes_regardless():
    m = _manifest(cost_per_1k_tokens=999.0)
    req = _request(cost_ceiling=None)
    assert _score_manifest(m, req) is not None


# ---------------------------------------------------------------------------
# LocalManifestLoader
# ---------------------------------------------------------------------------

def test_manifest_loader_loads_valid_file(tmp_path):
    data = [{"model_id": "a/b", "adapter_version": "1.0.0", "task_types": ["classify"]}]
    p = tmp_path / "manifests.json"
    _write_manifests(p, data)
    loader = LocalManifestLoader(str(p))
    manifests = loader.get_manifests()
    assert len(manifests) == 1
    assert manifests[0].model_id == "a/b"


def test_manifest_loader_missing_file_returns_empty(tmp_path):
    loader = LocalManifestLoader(str(tmp_path / "nonexistent.json"))
    assert loader.get_manifests() == []


def test_manifest_loader_invalid_json_retains_previous(tmp_path):
    p = tmp_path / "manifests.json"
    data = [{"model_id": "a/b", "adapter_version": "1.0.0"}]
    _write_manifests(p, data)
    loader = LocalManifestLoader(str(p))
    assert len(loader.get_manifests()) == 1

    p.write_text("NOT JSON", encoding="utf-8")
    loader._load()
    assert len(loader.get_manifests()) == 1  # retained previous


def test_manifest_loader_hot_reload(tmp_path):
    p = tmp_path / "manifests.json"
    _write_manifests(p, [{"model_id": "a/b", "adapter_version": "1.0.0"}])
    loader = LocalManifestLoader(str(p))
    loader.start_watching()

    _write_manifests(p, [
        {"model_id": "a/b", "adapter_version": "1.0.0"},
        {"model_id": "c/d", "adapter_version": "2.0.0"},
    ])
    # Force mtime to a future value so the watcher detects a change regardless
    # of filesystem timestamp granularity (Windows NTFS can batch same-second writes).
    future = time.time() + 10
    os.utime(p, (future, future))

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if len(loader.get_manifests()) == 2:
            break
        time.sleep(0.1)

    assert len(loader.get_manifests()) == 2


# ---------------------------------------------------------------------------
# LocalRouter
# ---------------------------------------------------------------------------

def test_local_router_returns_candidates(tmp_path):
    p = tmp_path / "m.json"
    _write_manifests(p, [{"model_id": "a/b", "adapter_version": "1.0.0", "task_types": ["classify"], "domains": ["general"]}])
    loader = LocalManifestLoader(str(p))
    router = LocalRouter(loader)
    resp = router.route(_request())
    assert len(resp.candidates) == 1
    assert resp.candidates[0].model_id == "a/b"


def test_local_router_filters_unavailable(tmp_path):
    p = tmp_path / "m.json"
    _write_manifests(p, [{"model_id": "a/b", "adapter_version": "1.0.0", "available": False}])
    loader = LocalManifestLoader(str(p))
    router = LocalRouter(loader)
    resp = router.route(_request())
    assert resp.candidates == []
    assert resp.filtered_out[0].model_id == "a/b"


def test_local_router_sorts_by_score(tmp_path):
    p = tmp_path / "m.json"
    _write_manifests(p, [
        {"model_id": "low/q", "adapter_version": "1.0.0", "task_types": ["classify"], "domains": ["general"], "quality_score": 0.5},
        {"model_id": "high/q", "adapter_version": "1.0.0", "task_types": ["classify"], "domains": ["general"], "quality_score": 0.9},
    ])
    loader = LocalManifestLoader(str(p))
    router = LocalRouter(loader)
    resp = router.route(_request())
    assert resp.candidates[0].model_id == "high/q"


def test_local_router_respects_limit(tmp_path):
    p = tmp_path / "m.json"
    models = [{"model_id": f"m/{i}", "adapter_version": "1.0.0", "task_types": ["classify"], "domains": ["general"]} for i in range(10)]
    _write_manifests(p, models)
    loader = LocalManifestLoader(str(p))
    router = LocalRouter(loader)
    req = _request(limit=3)
    resp = router.route(req)
    assert len(resp.candidates) <= 3


def test_local_router_empty_manifests(tmp_path):
    p = tmp_path / "m.json"
    _write_manifests(p, [])
    loader = LocalManifestLoader(str(p))
    router = LocalRouter(loader)
    resp = router.route(_request())
    assert resp.candidates == []


# ---------------------------------------------------------------------------
# LocalCalibrationWriter
# ---------------------------------------------------------------------------

def test_cal_writer_writes_jsonl(tmp_path):
    p = tmp_path / "cal.jsonl"
    writer = LocalCalibrationWriter(str(p))
    writer.write({"model_id": "a/b", "latency_ms": 42})
    writer.write({"model_id": "c/d", "latency_ms": 99})
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["model_id"] == "a/b"


def test_cal_writer_handles_unwritable_path(tmp_path):
    writer = LocalCalibrationWriter("/dev/null/cannot/write.jsonl")
    writer.write({"model_id": "x"})  # must not raise


def test_cal_writer_thread_safe(tmp_path):
    p = tmp_path / "cal.jsonl"
    writer = LocalCalibrationWriter(str(p))
    threads = [threading.Thread(target=writer.write, args=({"i": i},)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 20


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------

def test_is_local_mode_false_by_default():
    assert is_local_mode() is False


def test_get_router_none_when_not_local():
    assert get_router() is None


def test_get_cal_writer_none_when_not_local():
    assert get_cal_writer() is None
