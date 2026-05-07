# SYNAPSE Adapter SDK

The intelligence layer above the AI protocol layer.

Without SYNAPSE, connecting 4 specialized AI models requires 6 custom
connectors. 10 models requires 45. Each one breaks when either model's
schema changes.

With SYNAPSE, write one `ingress` and one `egress` function per model —
and achieve permanent interoperability with every other registered model.

## Install


```bash
pip install synapse-adapter-sdk
```



## Write your first adapter


```python
from synapse_sdk import AdapterBase, CanonicalIR
from typing import Any

class MyModelAdapter(AdapterBase):
    MODEL_ID = "my-org/my-model-v1.0"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        return { "input": ir.payload.content }

    def egress(self, output: dict, original_ir: CanonicalIR, latency_ms: int) -> CanonicalIR:
        updated = original_ir.copy()
        updated.provenance.append(self.build_provenance(
            confidence=output["score"],
            latency_ms=latency_ms,
        ))
        return updated
```



## Validate your adapter


```bash
synapse-validate --adapter my_module.MyModelAdapter --all-fixtures
```



## What SYNAPSE is not

SYNAPSE does not compete with MCP or A2A. It builds on top of them.
MCP connects agents to tools. A2A connects agents to each other.
SYNAPSE connects specialist models with incompatible schemas — and makes
routing between them smarter over time.

## Links

- [Canonical IR Specification](https://github.com/synapse-ir/spec)
- [Model Registry](https://github.com/synapse-ir/registry)
- [Community Adapters](https://github.com/synapse-ir/adapters)
