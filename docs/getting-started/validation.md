# Adapter Validation

Every adapter must pass 13 validation rules before it can be registered
with the SYNAPSE ecosystem.

## Run the validator


```bash
synapse-validate --adapter my_module.MyAdapter
synapse-validate --adapter my_module.MyAdapter --all-fixtures
```



## The 13 validation rules

| Rule | Level | Description |
|------|-------|-------------|
| INGRESS_NOT_NULL | MUST | ingress() must never return null or undefined |
| EGRESS_RETURNS_IR | MUST | egress() must return a valid CanonicalIR object |
| PROVENANCE_APPENDED | MUST | egress() must append exactly one ProvenanceEntry |
| PROVENANCE_IMMUTABLE | MUST | egress() must not modify any existing ProvenanceEntry |
| TASK_HEADER_CARRIED | MUST | egress() output task_header must equal original |
| COMPLIANCE_CARRIED | MUST | egress() compliance_envelope must equal original |
| NO_NETWORK_CALLS | MUST | Adapter functions must be pure — no I/O |
| CONFIDENCE_RANGE | MUST | ProvenanceEntry.confidence must be in [0.0, 1.0] |
| MODEL_ID_MATCH | MUST | ProvenanceEntry.model_id must match adapter.modelId |
| VERSION_SEMVER | MUST | adapter_version must be valid semver |
| LATENCY_POSITIVE | SHOULD | latency_ms should be > 0 |
| COST_NON_NEGATIVE | SHOULD | cost_usd, if present, should be >= 0.0 |
| CONTENT_PRESERVED | SHOULD | payload.content should not be mutated by egress |

## Common failures and fixes

**PROVENANCE_IMMUTABLE**

```python
# Wrong
ir.provenance[0].confidence = 0.9

# Right
updated.provenance.append(self.build_provenance(confidence=0.9, latency_ms=latency_ms))
```



**TASK_HEADER_CARRIED**

```python
updated = original_ir.clone()  # clone() performs deep copy, carries task_header
```



## Running fixtures in tests

Use assert_valid_on() to run a specific fixture through your adapter
inside a test suite:

```python
import pytest
from synapse_sdk.testing import AdapterValidator
from synapse_sdk.testing.fixtures import ALL_FIXTURES
from my_model.my_adapter import MyAdapter

@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_all_fixtures(fixture):
    AdapterValidator(MyAdapter()).assert_valid_on(fixture)
```
