"""SYNAPSE Adapter SDK — §G-S05 Local Development Mode.

When SYNAPSE_LOCAL_MODE=true the SDK replaces external registry calls with:
  - Manifest loading from SYNAPSE_LOCAL_MANIFEST_PATH (JSON array)
  - File-polling hot reload — no restart needed on manifest change
  - In-process routing that scores manifests with the same algorithm as the registry
  - Calibration signal logging to SYNAPSE_LOCAL_CAL_LOG (JSONL append)
  - All auth checks bypassed
  - Startup banner printed to stdout

This module auto-initialises on import when SYNAPSE_LOCAL_MODE=true.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from synapse_sdk.cache import (
    RouteCandidate,
    RouteRequest,
    RouteResponse,
)

log = logging.getLogger(__name__)

_BANNER = (
    "\n"
    "╔══════════════════════════════════════════════════════════════╗\n"
    "║  SYNAPSE running in LOCAL MODE — not for production          ║\n"
    "║  Registry : local file    │  Auth : bypassed                 ║\n"
    "║  Set SYNAPSE_LOCAL_MODE=false to re-enable production mode   ║\n"
    "╚══════════════════════════════════════════════════════════════╝\n"
)

_banner_printed = False
_banner_lock = threading.Lock()


def _print_banner() -> None:
    global _banner_printed
    with _banner_lock:
        if not _banner_printed:
            print(_BANNER, flush=True)
            _banner_printed = True


# ---------------------------------------------------------------------------
# Manifest schema (mirrors registry GET /v1/models response items)
# ---------------------------------------------------------------------------

@dataclass
class CapabilityManifest:
    """SDK-side mirror of a registry model manifest entry.

    The local JSON file uses the same field names as the registry API, so a
    developer can seed it via:
        curl https://registry.synapse-ir.io/v1/models > synapse_local_manifests.json
    """

    model_id:            str
    adapter_version:     str
    task_types:          list[str]   = field(default_factory=list)
    domains:             list[str]   = field(default_factory=list)
    compliance_tags:     list[str]   = field(default_factory=list)
    latency_p50_ms:      int         = 100
    latency_p99_ms:      int         = 500
    cost_per_1k_tokens:  float | None = None
    quality_score:       float       = 0.8
    available:           bool        = True


# ---------------------------------------------------------------------------
# C1-alt: LocalManifestLoader — file-polling hot reload
# ---------------------------------------------------------------------------

class LocalManifestLoader:
    """Loads CapabilityManifest objects from a JSON file and hot-reloads on change.

    Polling interval: 1 second (inotify not used to remain cross-platform).
    On any load error the previous manifest list is retained and a warning is logged.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._manifests: list[CapabilityManifest] = []
        self._mtime: float = -1.0
        self._lock = threading.Lock()
        self._load()

    # -- Public API -------------------------------------------------------

    def get_manifests(self) -> list[CapabilityManifest]:
        with self._lock:
            return list(self._manifests)

    def start_watching(self) -> None:
        """Start the background polling thread (daemon — exits with the process)."""
        t = threading.Thread(
            target=self._poll_loop,
            name="synapse-local-manifest-watcher",
            daemon=True,
        )
        t.start()
        log.debug("local_manifest_watcher_started: path=%s", self._path)

    # -- Internals --------------------------------------------------------

    def _load(self) -> None:
        try:
            mtime = os.path.getmtime(self._path)
            with open(self._path, encoding="utf-8") as fh:
                raw: list[dict] = json.load(fh)
            manifests = [CapabilityManifest(**entry) for entry in raw]
            with self._lock:
                self._manifests = manifests
                self._mtime = mtime
            log.info(
                "local_manifest_loaded: path=%s count=%d",
                self._path,
                len(manifests),
            )
        except FileNotFoundError:
            log.warning(
                "local_manifest_not_found: path=%s — using empty manifest list",
                self._path,
            )
        except Exception as exc:
            log.warning(
                "local_manifest_load_error: path=%s error=%s — retaining previous list",
                self._path,
                exc,
            )

    def _poll_loop(self) -> None:
        while True:
            time.sleep(1.0)
            try:
                mtime = os.path.getmtime(self._path)
            except FileNotFoundError:
                continue
            except Exception as exc:
                log.debug("local_manifest_poll_error: %s", exc)
                continue

            with self._lock:
                prev_mtime = self._mtime
            if mtime != prev_mtime:
                log.info("local_manifest_changed: reloading path=%s", self._path)
                self._load()


# ---------------------------------------------------------------------------
# LocalRouter — same scoring algorithm as the registry
# ---------------------------------------------------------------------------

def _score_manifest(manifest: CapabilityManifest, request: RouteRequest) -> float | None:
    """Score a manifest against a routing request.

    Returns None when the manifest is filtered out (unavailable, wrong
    task_type/domain, missing compliance tags, over cost ceiling, under
    quality floor, or over latency budget).

    Scoring formula (matches registry v1 algorithm):
        score = quality_score * latency_factor
    where latency_factor = min(1.0, latency_budget_ms / latency_p50_ms)
    and falls back to 1.0 when budget or p50 is zero.
    """
    if not manifest.available:
        return None

    if manifest.model_id in (request.exclude_models or []):
        return None

    if request.task_type and request.task_type not in manifest.task_types:
        return None

    if request.domain and request.domain not in manifest.domains:
        return None

    required = set(request.compliance_tags or [])
    if required and not required.issubset(set(manifest.compliance_tags)):
        return None

    if (
        request.cost_ceiling is not None
        and manifest.cost_per_1k_tokens is not None
        and manifest.cost_per_1k_tokens > request.cost_ceiling
    ):
        return None

    if (
        request.quality_floor is not None
        and manifest.quality_score < request.quality_floor
    ):
        return None

    if (
        request.latency_budget_ms > 0
        and manifest.latency_p99_ms > request.latency_budget_ms
    ):
        return None

    latency_factor = 1.0
    if manifest.latency_p50_ms > 0 and request.latency_budget_ms > 0:
        latency_factor = min(1.0, request.latency_budget_ms / manifest.latency_p50_ms)

    return manifest.quality_score * latency_factor


class LocalRouter:
    """Routes requests against local manifests using the registry scoring algorithm."""

    def __init__(self, loader: LocalManifestLoader) -> None:
        self._loader = loader

    def route(self, request: RouteRequest) -> RouteResponse:
        manifests = self._loader.get_manifests()
        candidates:   list[RouteCandidate] = []
        filtered_out: list[RouteCandidate] = []

        for manifest in manifests:
            score = _score_manifest(manifest, request)
            rc = RouteCandidate(
                model_id=manifest.model_id,
                adapter_version=manifest.adapter_version,
                score=score if score is not None else 0.0,
                estimated_latency_ms=manifest.latency_p50_ms,
                estimated_cost_usd=manifest.cost_per_1k_tokens,
            )
            if score is not None:
                candidates.append(rc)
            else:
                filtered_out.append(rc)

        candidates.sort(key=lambda c: c.score, reverse=True)
        limit = request.limit if request.limit is not None else 5
        candidates = candidates[:limit]

        return RouteResponse(candidates=candidates, filtered_out=filtered_out)


# ---------------------------------------------------------------------------
# LocalCalibrationWriter — C5-alt: write signals to JSONL
# ---------------------------------------------------------------------------

class LocalCalibrationWriter:
    """Appends calibration signals to a JSONL file (local-mode C5 replacement).

    Thread-safe; failures are logged and silently dropped — identical
    semantics to the production CalibrationBuffer.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    def write(self, signal: dict[str, Any]) -> None:
        try:
            line = json.dumps(signal, default=str)
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception as exc:
            log.warning("local_cal_write_error: path=%s error=%s", self._path, exc)


# ---------------------------------------------------------------------------
# Module-level singletons — initialised once on import
# ---------------------------------------------------------------------------

_is_local_mode: bool = os.getenv("SYNAPSE_LOCAL_MODE", "false").lower() == "true"

_router: LocalRouter | None = None
_cal_writer: LocalCalibrationWriter | None = None


def is_local_mode() -> bool:
    """Return True when SYNAPSE_LOCAL_MODE=true."""
    return _is_local_mode


def get_router() -> LocalRouter | None:
    """Return the local router singleton, or None if not in local mode."""
    return _router


def get_cal_writer() -> LocalCalibrationWriter | None:
    """Return the local calibration writer singleton, or None if not in local mode."""
    return _cal_writer


def _init() -> None:
    global _router, _cal_writer

    if not _is_local_mode:
        return

    _print_banner()

    manifest_path = os.getenv(
        "SYNAPSE_LOCAL_MANIFEST_PATH", "./synapse_local_manifests.json"
    )
    cal_log_path = os.getenv("SYNAPSE_LOCAL_CAL_LOG", "./synapse_cal.jsonl")

    loader = LocalManifestLoader(manifest_path)
    loader.start_watching()

    _router = LocalRouter(loader)
    _cal_writer = LocalCalibrationWriter(cal_log_path)

    log.info(
        "local_mode_ready: manifest_path=%s cal_log=%s",
        manifest_path,
        cal_log_path,
    )


_init()

__all__ = [
    "CapabilityManifest",
    "LocalManifestLoader",
    "LocalRouter",
    "LocalCalibrationWriter",
    "is_local_mode",
    "get_router",
    "get_cal_writer",
]
