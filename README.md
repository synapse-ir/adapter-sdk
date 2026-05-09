# SYNAPSE Adapter SDK

SYNAPSE is a canonical intermediate representation (IR) protocol that lets AI models with incompatible schemas interoperate through a unified adapter interface.

Write **two functions** — connect your AI model to every other model in the ecosystem.

Without SYNAPSE: 4 models require 6 custom connectors. 10 models require 45.
Each breaks when either model's schema changes.

With SYNAPSE: write one `ingress` and one `egress` adapter. Done.
Your model is immediately composable with every other registered model.

## Install

```bash
pip install synapse-adapter-sdk
```

## Write your first adapter

```python
from synapse_sdk import AdapterBase, CanonicalIR, ProvenanceEntry
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

## Validate

```bash
synapse-validate --adapter my_module.MyModelAdapter
```

## Documentation

- [Getting started](https://synapse-ir.github.io/adapter-sdk/getting-started/installation/)
- [Writing adapters](https://synapse-ir.github.io/adapter-sdk/getting-started/first-adapter/)
- [Canonical IR specification](https://github.com/synapse-ir/spec)
- [Registry](https://github.com/synapse-ir/registry)

## What SYNAPSE is not

SYNAPSE does not compete with MCP or A2A. It builds on top of them.
MCP connects agents to tools. A2A connects agents to each other.
SYNAPSE connects specialized models with incompatible schemas — and
makes routing between them smarter over time.

## Feedback and issues

Found a bug or have a feature request? Open an issue:
https://github.com/synapse-ir/adapter-sdk/issues

For security vulnerabilities, see [SECURITY.md](SECURITY.md) instead
of opening a public issue.

## License

MIT. See [LICENSE](LICENSE).
