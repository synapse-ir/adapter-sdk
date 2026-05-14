# AdapterBase

The abstract base class all SYNAPSE adapters must extend.

## Minimal example

```python
from synapse_sdk import AdapterBase, CanonicalIR
from synapse_sdk.types import Classification
from typing import Any

class MyAdapter(AdapterBase):
    MODEL_ID = "my-org/my-model-v1.0"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        return {"text": ir.payload.content or ""}

    def egress(
        self,
        model_output: Any,
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        updated = original_ir.clone()
        label = str(model_output[0].get("label", "")) if model_output else ""
        score = float(model_output[0].get("score", 0.0)) if model_output else 0.0
        updated.payload.labels = [Classification(label=label, score=score)]
        updated.provenance.append(
            self.build_provenance(confidence=score, latency_ms=latency_ms)
        )
        return updated
```

---

## Required class attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `MODEL_ID` | `str` | Globally unique model identifier — must match the registry entry exactly |
| `ADAPTER_VERSION` | `str` | Semver string (e.g. `"1.0.0"`) — bump when adapter logic changes |

---

## ingress()

```python
def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
```

Converts the canonical IR into whatever format the model natively expects.

**Contract:**

- MUST be pure — no network calls, no file I/O, no side effects, no persistent state
- MUST NOT raise on valid IR — return a best-effort transformation
- MUST NOT return `None` — return `{}` if there is nothing to pass
- MUST NOT call the model — ingress only transforms the input

---

## egress()

```python
def egress(
    self,
    model_output: Any,
    original_ir: CanonicalIR,
    latency_ms: int,
) -> CanonicalIR:
```

Converts the model's output back to canonical IR and records the provenance entry.

**Contract:**

- MUST return a valid `CanonicalIR`
- MUST append exactly one `ProvenanceEntry` via `self.build_provenance()`
- MUST NOT modify any existing `ProvenanceEntry` in the provenance chain
- MUST carry `task_header` and `compliance_envelope` forward unchanged
- MUST be pure — no network calls, no side effects
- MUST start from `original_ir.clone()`, not from scratch

```python
def egress(self, model_output, original_ir, latency_ms):
    updated = original_ir.clone()           # deep copy, carries all fields
    # ... populate updated.payload ...
    updated.provenance.append(
        self.build_provenance(confidence=0.9, latency_ms=latency_ms)
    )
    return updated
```

---

## build_provenance()

```python
def build_provenance(
    self,
    confidence: float,
    latency_ms: int,
    *,
    cost_usd: float | None = None,
    token_count: int | None = None,
    warnings: list[str] | None = None,
    timestamp_unix: int | None = None,
) -> ProvenanceEntry:
```

Constructs a `ProvenanceEntry` pre-filled with this adapter's `MODEL_ID` and `ADAPTER_VERSION`. Always use this method rather than constructing `ProvenanceEntry` directly.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `confidence` | `float` | yes | Model confidence, `[0.0, 1.0]` |
| `latency_ms` | `int` | yes | Wall-clock time for this inference call, `>= 0` |
| `cost_usd` | `float \| None` | no | Inference cost in USD, `>= 0.0` |
| `token_count` | `int \| None` | no | Tokens consumed |
| `warnings` | `list[str] \| None` | no | Non-fatal advisory messages |
| `timestamp_unix` | `int \| None` | no | Override timestamp; defaults to `int(time.time())` |

### Raises

`AdapterConfigurationError` (G-C06 envelope) when:

- `confidence` is outside `[0.0, 1.0]`
- `latency_ms` is negative
- `cost_usd` is negative

### Example

```python
import time

t0 = time.monotonic()
raw = model(inputs)
latency_ms = int((time.monotonic() - t0) * 1000)

updated.provenance.append(
    self.build_provenance(
        confidence=raw["score"],
        latency_ms=latency_ms,
        cost_usd=raw.get("cost"),
        token_count=raw.get("tokens"),
    )
)
```

---

## AdapterConfigurationError

Raised by `build_provenance()` when an argument is invalid. Serialises to a JSON G-C06 error envelope.

```python
try:
    entry = adapter.build_provenance(confidence=1.5, latency_ms=10)
except AdapterConfigurationError as exc:
    print(exc.envelope["field"])    # "confidence"
    print(exc.envelope["message"])  # human-readable description
```

`exc.envelope` keys: `error`, `message`, `field`, `expected`, `received`, `recommendation`.
