# Writing Your First Adapter

This guide takes you from zero to a working, validated adapter in under
30 minutes. We use a simple text classifier as the example.

## Step 1 - Install the SDK

pip install synapse-adapter-sdk

## Step 2 - Understand the contract

Every SYNAPSE adapter implements two functions:

- ingress(ir: CanonicalIR) -> dict
  Converts the canonical IR into whatever your model natively expects.

- egress(output: Any, original_ir: CanonicalIR, latency_ms: int) -> CanonicalIR
  Converts your model's output back to canonical IR and appends a ProvenanceEntry.

Both functions must be pure: no network calls, no side effects, no persistent state.

## Step 3 - Create your adapter folder

Each adapter lives in its own folder:

  your_model_name/
    your_model_adapter.py
    README.md
    tests/
      test_your_model_adapter.py

## Step 4 - Write the adapter

from __future__ import annotations
from typing import Any
from synapse_sdk import AdapterBase, CanonicalIR
from synapse_sdk.types import Classification


class MyClassifierAdapter(AdapterBase):
    MODEL_ID = "my-org/my-classifier-v1"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        return {"text": ir.payload.content or ""}

    def egress(
        self,
        output: Any,
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        updated = original_ir.clone()

        label = ""
        score = 0.0
        if isinstance(output, list) and output:
            label = str(output[0].get("label", ""))
            score = float(output[0].get("score", 0.0))

        updated.payload.labels = [Classification(label=label, score=score)]
        updated.provenance.append(
            self.build_provenance(confidence=score, latency_ms=latency_ms)
        )
        return updated

Key rules:
- Always use original_ir.clone(), never original_ir.copy()
- Always append exactly one ProvenanceEntry via self.build_provenance()
- Never call the model inside ingress or egress
- Handle edge cases without raising exceptions

## Step 5 - Write tests

Tests must use mock output only. Never call the real model in tests.

import pytest
from synapse_sdk.testing import AdapterValidator
from synapse_sdk.testing.fixtures import ALL_FIXTURES
from your_model.your_model_adapter import MyClassifierAdapter


@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_all_fixtures(fixture):
    AdapterValidator(MyClassifierAdapter()).assert_valid_on(fixture)


def test_egress_stores_label():
    adapter = MyClassifierAdapter()
    # build a minimal CanonicalIR for testing
    # see the SDK testing docs for helpers
    mock_output = [{"label": "positive", "score": 0.91}]
    # ... assert payload.labels[0].label == "positive"


def test_validator_passes():
    AdapterValidator(MyClassifierAdapter()).assert_valid()

## Step 6 - Run the full audit

uv run pytest your_model/tests/ -v --tb=short
uv run python -c "from synapse_sdk.testing import AdapterValidator; from your_model.your_model_adapter import MyClassifierAdapter; AdapterValidator(MyClassifierAdapter()).assert_valid(); print('Validator: all rules passed')"
uv run ruff check your_model/
uv run mypy your_model/your_model_adapter.py

All four must be clean before opening a pull request.

## Step 7 - Open a pull request

See CONTRIBUTING.md for the full PR checklist.
