# AdapterBase

The abstract base class all SYNAPSE adapters must extend.

## Usage


```python
from synapse_sdk import AdapterBase, CanonicalIR
from typing import Any

class MyAdapter(AdapterBase):
    MODEL_ID = "my-org/my-model-v1.0"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        raise NotImplementedError

    def egress(self, output: dict, original_ir: CanonicalIR, latency_ms: int) -> CanonicalIR:
        raise NotImplementedError
```



## build_provenance()


```python
entry = self.build_provenance(
    confidence=0.94,
    latency_ms=43,
    cost_usd=0.00009,
    token_count=512,
)
```



## Required class attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| MODEL_ID | str | Globally unique model identifier |
| ADAPTER_VERSION | str | Semver of this adapter |
