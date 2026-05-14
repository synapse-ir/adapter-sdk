# SPDX-FileCopyrightText: 2024 Chris Widmer
# SPDX-License-Identifier: MIT
"""synapse-validate — CLI for validating SYNAPSE adapters against standard fixtures.

Usage examples::

    # Validate against the built-in minimal fixture
    synapse-validate --adapter mypackage.adapters.MyAdapter

    # Validate against a custom fixture file
    synapse-validate --adapter mypackage.adapters.MyAdapter --fixture ./my_fixture.json

    # Validate against all 20 standard §9 G-S06 fixtures
    synapse-validate --adapter mypackage.adapters.MyAdapter --all-fixtures

Exit codes:
    0  All MUST rules passed (warnings are shown but do not affect exit code)
    1  One or more MUST rules failed
    2  Usage error (bad arguments, adapter import failure, etc.)
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from synapse_sdk.types import CanonicalIR
    from synapse_sdk.validator import AdapterValidationResult, ValidationFailure

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_NO_COLOR = (
    not sys.stdout.isatty()
    or os.getenv("NO_COLOR") is not None
    or os.getenv("TERM") == "dumb"
)

# Detect Unicode support: Windows cmd/ps without UTF-8 codepage needs ASCII glyphs
try:
    "─✓✗⚠".encode(sys.stdout.encoding or "ascii")
    _NO_UNICODE = False
except (UnicodeEncodeError, LookupError):
    _NO_UNICODE = True


def _glyph(unicode_char: str, ascii_fallback: str) -> str:
    return ascii_fallback if _NO_UNICODE else unicode_char


_HR:    Callable[[], str] = lambda: _glyph("─", "-") * 60  # noqa: E731
_PASS:  Callable[[], str] = lambda: _glyph("✓", "+")       # noqa: E731
_FAIL:  Callable[[], str] = lambda: _glyph("✗", "x")       # noqa: E731
_WARN:  Callable[[], str] = lambda: _glyph("⚠", "!")       # noqa: E731
_ARROW: Callable[[], str] = lambda: _glyph("→", "->")      # noqa: E731


def _green(s: str) -> str:
    return s if _NO_COLOR else f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return s if _NO_COLOR else f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return s if _NO_COLOR else f"\033[33m{s}\033[0m"


def _bold(s: str) -> str:
    return s if _NO_COLOR else f"\033[1m{s}\033[0m"


def _dim(s: str) -> str:
    return s if _NO_COLOR else f"\033[2m{s}\033[0m"


# ---------------------------------------------------------------------------
# Adapter loading
# ---------------------------------------------------------------------------

def _load_adapter(dotted_path: str) -> Any:
    """Import a class by dotted path (e.g. 'mypackage.module.ClassName').

    Raises SystemExit(2) with a descriptive message on any failure.
    """
    if "." not in dotted_path:
        _die(
            f"--adapter must be a dotted path to a class, e.g. 'mypackage.MyAdapter'. "
            f"Got: {dotted_path!r}",
            code=2,
        )

    module_path, class_name = dotted_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        _die(
            f"Cannot import module {module_path!r}: {exc}\n"
            f"  Make sure the package is installed and PYTHONPATH is set correctly.",
            code=2,
        )

    cls = getattr(module, class_name, None)
    if cls is None:
        _die(
            f"Module {module_path!r} has no attribute {class_name!r}.\n"
            f"  Available names: {', '.join(n for n in dir(module) if not n.startswith('_'))}",
            code=2,
        )

    try:
        instance = cls()
    except Exception as exc:
        _die(
            f"Failed to instantiate {dotted_path!r}: {type(exc).__name__}: {exc}",
            code=2,
        )

    return instance


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def _load_fixture_file(path: str) -> CanonicalIR:
    from synapse_sdk.types import CanonicalIR

    try:
        with open(path, encoding="utf-8") as fh:
            data = fh.read()
    except OSError as exc:
        _die(f"Cannot read fixture file {path!r}: {exc}", code=2)

    try:
        return CanonicalIR.from_json(data)
    except Exception as exc:
        _die(
            f"Fixture file {path!r} is not a valid CanonicalIR: {exc}",
            code=2,
        )


def _load_all_fixtures() -> list[CanonicalIR]:
    try:
        from synapse_sdk.testing.fixtures import ALL_FIXTURES
        return ALL_FIXTURES
    except Exception as exc:
        _die(f"Failed to load standard fixture library: {exc}", code=2)


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------

def _print_result(
    result: AdapterValidationResult,
    adapter_name: str,
    fixture_label: str,
) -> None:
    """Print a single fixture's result in coloured terminal format."""
    status = _green("PASS") if result.passed else _red("FAIL")
    print(f"  [{status}] {_bold(fixture_label)}")

    for err in result.errors:
        print(f"         {_red(_FAIL())} [{err.rule_id}] {err.message}")
        rec = _RULE_RECOMMENDATIONS.get(err.rule_id)
        if rec:
            print(f"           {_dim(_ARROW())} {_dim(rec)}")

    for warn in result.warnings:
        print(f"         {_yellow(_WARN())} [{warn.rule_id}] {warn.message}")


def _run_single(adapter: Any, fixture: CanonicalIR, label: str) -> AdapterValidationResult:
    from synapse_sdk.validator import AdapterValidator

    validator = AdapterValidator(adapter, fixtures=[fixture])
    return validator.run()


# ---------------------------------------------------------------------------
# Lazy import of rule recommendations
# ---------------------------------------------------------------------------

def _get_recommendations() -> dict[str, str]:
    from synapse_sdk.validator import _RULE_RECOMMENDATIONS
    return _RULE_RECOMMENDATIONS


_RULE_RECOMMENDATIONS: dict[str, str] = {}  # populated lazily in main()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _die(msg: str, code: int = 1) -> NoReturn:
    print(f"{_red('error:')} {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    global _RULE_RECOMMENDATIONS

    parser = argparse.ArgumentParser(
        prog="synapse-validate",
        description="Validate a SYNAPSE adapter against standard fixtures (§9 G-S06).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  synapse-validate --adapter mypackage.MyAdapter\n"
            "  synapse-validate --adapter mypackage.MyAdapter --fixture ./fixture.json\n"
            "  synapse-validate --adapter mypackage.MyAdapter --all-fixtures\n"
        ),
    )
    parser.add_argument(
        "--adapter",
        required=True,
        metavar="MODULE.ClassName",
        help="Dotted import path to the AdapterBase subclass to validate.",
    )
    parser.add_argument(
        "--fixture",
        metavar="PATH",
        help="Path to a single CanonicalIR JSON fixture file.",
    )
    parser.add_argument(
        "--all-fixtures",
        action="store_true",
        help="Run all 20 standard §9 G-S06 fixtures.",
    )
    args = parser.parse_args(argv)

    if args.fixture and args.all_fixtures:
        _die("--fixture and --all-fixtures are mutually exclusive.", code=2)

    # Load rule recommendations for display
    _RULE_RECOMMENDATIONS = _get_recommendations()

    # Load adapter
    adapter = _load_adapter(args.adapter)
    adapter_name = type(adapter).__name__

    print()
    print(_bold(f"synapse-validate — {adapter_name}"))
    print(_dim(f"  MODEL_ID        : {getattr(adapter, 'MODEL_ID', '(unknown)')}"))
    print(_dim(f"  ADAPTER_VERSION : {getattr(adapter, 'ADAPTER_VERSION', '(unknown)')}"))
    print()

    # Determine fixture set
    if args.all_fixtures:
        from synapse_sdk.testing.fixtures import ALL_FIXTURES, FIXTURE_NAMES
        fixtures = ALL_FIXTURES
        labels = FIXTURE_NAMES
        mode_label = "all 20 standard fixtures"
    elif args.fixture:
        fixtures = [_load_fixture_file(args.fixture)]
        labels = [os.path.basename(args.fixture)]
        mode_label = f"fixture: {args.fixture}"
    else:
        from synapse_sdk.validator import _minimal_ir
        fixtures = [_minimal_ir()]
        labels = ["built-in minimal fixture"]
        mode_label = "built-in minimal fixture"

    print(f"Running {_bold(mode_label)} ...")
    print()

    total = len(fixtures)
    passed = 0
    failed = 0

    all_errors:   list[ValidationFailure] = []
    all_warnings: list[ValidationFailure] = []

    for fixture, label in zip(fixtures, labels, strict=False):
        result = _run_single(adapter, fixture, label)
        _print_result(result, adapter_name, label)

        if result.passed:
            passed += 1
        else:
            failed += 1

        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

    # Summary
    print()
    print(_HR())
    if failed == 0:
        verdict = _green(f"{_PASS()} PASSED -- {passed}/{total} fixtures")
    else:
        verdict = _red(f"{_FAIL()} FAILED -- {failed}/{total} fixtures failed")

    print(f"  {verdict}")

    if all_warnings:
        print(f"  {_yellow(f'{len(all_warnings)} warning(s)')} (SHOULD-level, does not affect exit code)")

    if failed > 0:
        print()
        print(
            f"  Fix all {_red('MUST')}-level errors before publishing this adapter.\n"
            "  See https://docs.synapse-ir.io/adapters/validation for rule details."
        )

    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
