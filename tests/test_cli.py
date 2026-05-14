"""Tests for synapse_sdk.cli — synapse-validate entry point."""
from __future__ import annotations

import uuid

import pytest

from synapse_sdk.cli import (
    _bold,
    _dim,
    _glyph,
    _green,
    _red,
    _yellow,
    _load_adapter,
    _load_all_fixtures,
    main,
)
from synapse_sdk.types import CanonicalIR, Domain, Payload, TaskHeader, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_fixture_json(tmp_path) -> str:
    ir = CanonicalIR(
        ir_version="1.0.0",
        message_id=str(uuid.uuid4()),
        task_header=TaskHeader(
            task_type=TaskType.extract,
            domain=Domain.general,
            priority=2,
            latency_budget_ms=500,
        ),
        payload=Payload(modality="text", content="Hello world"),
    )
    p = tmp_path / "fixture.json"
    p.write_text(ir.to_json(), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Colour / glyph helpers
# ---------------------------------------------------------------------------

def test_glyph_returns_unicode_when_supported():
    result = _glyph("✓", "+")
    assert result in ("✓", "+")


def test_glyph_ascii_fallback():
    from synapse_sdk import cli as cli_mod
    original = cli_mod._NO_UNICODE
    try:
        cli_mod._NO_UNICODE = True
        assert _glyph("✓", "+") == "+"
    finally:
        cli_mod._NO_UNICODE = original


def test_color_functions_return_strings():
    for fn in (_green, _red, _yellow, _bold, _dim):
        result = fn("test")
        assert isinstance(result, str)
        assert "test" in result


def test_color_functions_no_color_mode():
    from synapse_sdk import cli as cli_mod
    original = cli_mod._NO_COLOR
    try:
        cli_mod._NO_COLOR = True
        assert _green("x") == "x"
        assert _red("x") == "x"
        assert _yellow("x") == "x"
        assert _bold("x") == "x"
        assert _dim("x") == "x"
    finally:
        cli_mod._NO_COLOR = original


# ---------------------------------------------------------------------------
# _load_adapter
# ---------------------------------------------------------------------------

def test_load_adapter_success():
    adapter = _load_adapter("adapters.ner_bert_adapter.NERBertAdapter")
    assert adapter.MODEL_ID == "dslim/bert-base-NER"


def test_load_adapter_no_dot_exits_2():
    with pytest.raises(SystemExit) as exc:
        _load_adapter("NoDotPath")
    assert exc.value.code == 2


def test_load_adapter_missing_module_exits_2():
    with pytest.raises(SystemExit) as exc:
        _load_adapter("no_such_package.NoClass")
    assert exc.value.code == 2


def test_load_adapter_missing_class_exits_2():
    with pytest.raises(SystemExit) as exc:
        _load_adapter("adapters.ner_bert_adapter.NonExistent")
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# _load_all_fixtures
# ---------------------------------------------------------------------------

def test_load_all_fixtures_returns_20():
    fixtures = _load_all_fixtures()
    assert len(fixtures) == 20


# ---------------------------------------------------------------------------
# main() — minimal fixture (no --fixture, no --all-fixtures)
# ---------------------------------------------------------------------------

def test_main_minimal_fixture_passes(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--adapter", "adapters.ner_bert_adapter.NERBertAdapter"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "PASS" in out or "pass" in out.lower()


def test_main_requires_adapter_flag():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# main() — --all-fixtures
# ---------------------------------------------------------------------------

def test_main_all_fixtures_passes(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--adapter", "adapters.ner_bert_adapter.NERBertAdapter", "--all-fixtures"])
    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# main() — --fixture
# ---------------------------------------------------------------------------

def test_main_single_fixture_passes(tmp_path, capsys):
    path = _minimal_fixture_json(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["--adapter", "adapters.ner_bert_adapter.NERBertAdapter", "--fixture", path])
    assert exc.value.code == 0


def test_main_fixture_and_all_fixtures_are_exclusive(capsys):
    with pytest.raises(SystemExit) as exc:
        main([
            "--adapter", "adapters.ner_bert_adapter.NERBertAdapter",
            "--fixture", "some/path.json",
            "--all-fixtures",
        ])
    assert exc.value.code == 2


def test_main_missing_fixture_file_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main([
            "--adapter", "adapters.ner_bert_adapter.NERBertAdapter",
            "--fixture", "/nonexistent/fixture.json",
        ])
    assert exc.value.code == 2


def test_main_invalid_fixture_json_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([
            "--adapter", "adapters.ner_bert_adapter.NERBertAdapter",
            "--fixture", str(bad),
        ])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# main() — bad adapter paths
# ---------------------------------------------------------------------------

def test_main_bad_adapter_no_dot_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--adapter", "NoDot"])
    assert exc.value.code == 2


def test_main_bad_adapter_missing_module_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--adapter", "no_such_package.NoClass"])
    assert exc.value.code == 2


def test_main_bad_adapter_missing_class_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--adapter", "adapters.ner_bert_adapter.NonExistent"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# main() — failing adapter produces exit code 1
# ---------------------------------------------------------------------------

def test_main_failing_adapter_exits_1(tmp_path, capsys):
    """An adapter that returns None from ingress() must produce exit 1."""
    bad_adapter = tmp_path / "bad_adapter.py"
    bad_adapter.write_text(
        """
from synapse_sdk import AdapterBase, CanonicalIR
from synapse_sdk.types import Payload
from typing import Any

class BadAdapter(AdapterBase):
    MODEL_ID = "test/bad"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir):
        return None  # violates INGRESS_NOT_NULL

    def egress(self, output, original_ir, latency_ms):
        updated = original_ir.clone()
        updated.provenance.append(self.build_provenance(confidence=0.5, latency_ms=latency_ms))
        return updated
""",
        encoding="utf-8",
    )
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(SystemExit) as exc:
            main(["--adapter", "bad_adapter.BadAdapter"])
        assert exc.value.code == 1
    finally:
        sys.path.pop(0)
        sys.modules.pop("bad_adapter", None)
