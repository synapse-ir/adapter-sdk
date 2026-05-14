# AdapterValidator

Validates an adapter against all 13 conformance rules before it can be published.

## Usage

```python
from synapse_sdk import AdapterValidator
from my_module import MyAdapter

validator = AdapterValidator(MyAdapter())

# Run all rules and inspect results
result = validator.run()
print(result.passed)        # True / False
print(result.summary())     # human-readable report

# Raise on any MUST failure
validator.assert_valid()

# Run against a specific fixture
from synapse_sdk.testing.fixtures import ALL_FIXTURES
validator.assert_valid_on(ALL_FIXTURES[0])

# Parametrize across all 20 fixtures in pytest
import pytest

@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_all_fixtures(fixture):
    AdapterValidator(MyAdapter()).assert_valid_on(fixture)
```

Pass fixtures to the constructor to run behavioural rules against multiple IRs:

```python
validator = AdapterValidator(MyAdapter(), fixtures=ALL_FIXTURES)
result = validator.run()
```

---

## CLI

```bash
synapse-validate --adapter my_module.MyAdapter
synapse-validate --adapter my_module.MyAdapter --all-fixtures
synapse-validate --adapter my_module.MyAdapter --fixture path/to/fixture.json
```

---

## The 13 validation rules

| Rule | Level | Description |
|------|-------|-------------|
| `INGRESS_NOT_NULL` | MUST | `ingress()` must never return `None` |
| `EGRESS_RETURNS_IR` | MUST | `egress()` must return a valid `CanonicalIR` |
| `PROVENANCE_APPENDED` | MUST | `egress()` must append exactly one `ProvenanceEntry` |
| `PROVENANCE_IMMUTABLE` | MUST | `egress()` must not modify any existing `ProvenanceEntry` |
| `TASK_HEADER_CARRIED` | MUST | `egress()` output `task_header` must equal the original |
| `COMPLIANCE_CARRIED` | MUST | `egress()` `compliance_envelope` must equal the original |
| `NO_NETWORK_CALLS` | MUST | Adapter functions must be pure — no I/O |
| `CONFIDENCE_RANGE` | MUST | `ProvenanceEntry.confidence` must be in `[0.0, 1.0]` |
| `MODEL_ID_MATCH` | MUST | `ProvenanceEntry.model_id` must match `adapter.MODEL_ID` |
| `VERSION_SEMVER` | MUST | `ADAPTER_VERSION` must be valid semver (`X.Y.Z`) |
| `LATENCY_POSITIVE` | SHOULD | `latency_ms` should be `> 0` |
| `COST_NON_NEGATIVE` | SHOULD | `cost_usd`, if present, should be `>= 0.0` |
| `CONTENT_PRESERVED` | SHOULD | `payload.content` should not be mutated by `egress()` |

`MUST` failures block publication. `SHOULD` failures produce warnings.

---

## Result types

### AdapterValidationResult

Returned by `validator.run()`.

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `bool` | `True` when no MUST rules failed |
| `errors` | `list[ValidationFailure]` | MUST-level failures |
| `warnings` | `list[ValidationFailure]` | SHOULD-level failures |

```python
result = validator.run()
if not result.passed:
    for failure in result.errors:
        print(failure.rule_id, failure.message)
```

`result.summary()` returns a formatted multi-line string of all errors and warnings.

### ValidationFailure

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | `str` | Rule identifier, e.g. `"PROVENANCE_APPENDED"` |
| `message` | `str` | Human-readable description of what failed and how to fix it |
| `severity` | `Severity` | `MUST` or `SHOULD` |

`failure.to_envelope()` returns a G-C06 JSON envelope dict.

### Severity

| Value | Meaning |
|-------|---------|
| `MUST` | Hard failure — adapter is rejected |
| `SHOULD` | Warning — adapter may be published with advisory |

---

## Exceptions

### AdapterValidationError

Raised by `assert_valid()` and `assert_valid_on()` when any MUST rule fails.

```python
from synapse_sdk import AdapterValidationError

try:
    AdapterValidator(MyAdapter()).assert_valid()
except AdapterValidationError as exc:
    print(exc.result.errors)   # list of ValidationFailure
    # exc itself serialises to a JSON G-C06 envelope
```

`exc.result` is the full `AdapterValidationResult`.

---

## Common failures and fixes

**PROVENANCE_IMMUTABLE**

```python
# Wrong — mutates an existing entry
ir.provenance[0].confidence = 0.9

# Right — only append new entries
updated.provenance.append(self.build_provenance(confidence=0.9, latency_ms=latency_ms))
```

**TASK_HEADER_CARRIED**

```python
# Wrong — reconstructs task_header from scratch
updated.task_header = TaskHeader(task_type="classify", ...)

# Right — clone() carries task_header automatically
updated = original_ir.clone()
```

**NO_NETWORK_CALLS**

```python
# Wrong — network call inside egress
def egress(self, output, original_ir, latency_ms):
    import requests
    extra = requests.get("https://api.example.com/context").json()
    ...

# Right — pass pre-fetched data via the IR (payload.data or context_ref)
def egress(self, output, original_ir, latency_ms):
    extra = original_ir.payload.data or {}
    ...
```

**INGRESS_NOT_NULL**

```python
# Wrong
def ingress(self, ir):
    if ir.payload.content is None:
        return None

# Right — return empty dict for edge cases
def ingress(self, ir):
    return {"text": ir.payload.content or ""}
```

---

## Running fixtures in tests

```python
import pytest
from synapse_sdk.testing import AdapterValidator
from synapse_sdk.testing.fixtures import ALL_FIXTURES
from my_model.my_adapter import MyAdapter

@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_all_fixtures(fixture):
    AdapterValidator(MyAdapter()).assert_valid_on(fixture)
```
