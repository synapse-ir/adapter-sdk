# Writing Your First Adapter

This guide takes you from zero to a working, validated adapter in under
30 minutes. We use a simple text classifier as the example.

## Step 1 — Install the SDK


```bash
pip install synapse-adapter-sdk
```



## Step 2 — Understand the contract

Every SYNAPSE adapter implements two functions:

- `ingress(ir: CanonicalIR) -> dict` — converts the canonical IR into
  whatever your model natively expects
- `egress(output: dict, original_ir: CanonicalIR, latency_ms: int) -> CanonicalIR`
  — converts your model's output back to canonical IR and appends a ProvenanceEntry

Both functions must be pure — no network calls, no side effects,
no persistent state.

## Step 3 — Write the adapter


```python
from synapse_sdk import AdapterBase, CanonicalIR
from typing import Any

class MyClassifierAdapter(AdapterBase):
    MODEL_ID = "my-org/my-classifier-v1.0"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        return {
            "text": ir.payload.content,
            "threshold": ir.task_header.quality_floor or 0.7,
        }

    def egress(
        self,
        output: dict[str, Any],
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        updated = original_ir.copy()
        updated.payload.data = {
            "label": output["label"],
            "confidence": output["score"],
        }
        updated.provenance.append(self.build_provenance(
            confidence=output["score"],
            latency_ms=latency_ms,
        ))
        return updated
```



## Step 4 — Validate your adapter


```bash
synapse-validate --adapter my_module.MyClassifierAdapter --all-fixtures
```



All 13 validation rules must pass. All 20 standard fixtures must pass.

## Step 5 — Register with the registry

Once your adapter passes validation, register your model:


```bash
curl -X POST https://registry.synapse-ir.io/v1/models \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @manifest.json
```



See the [Canonical IR Specification](https://github.com/synapse-ir/spec)
for the full manifest schema.
