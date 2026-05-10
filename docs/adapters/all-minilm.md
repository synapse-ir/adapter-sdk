# all-MiniLM-L6-v2 Adapter

Encodes text as 384-dimensional dense vectors for semantic similarity, search, and clustering.

## Model details

| Field | Value |
|-------|-------|
| Model | sentence-transformers/all-MiniLM-L6-v2 |
| Task | embed |
| Domain | general |
| License | Apache 2.0 |

## Install

```bash
pip install synapse-adapter-sdk
pip install sentence-transformers
```

## Verified output schema

`model.encode()` returns a `numpy.ndarray` of shape `(1, 384)`. The adapter maps this to:

- `payload.modality` — `"embedding"`
- `payload.vector` — `list[float]` of length 384
- `payload.vector_dim` — `384`
- `payload.embedding_model` — `"sentence-transformers/all-MiniLM-L6-v2"`

Example access:

```python
vector = result_ir.payload.vector       # list[float], length 384
dim    = result_ir.payload.vector_dim   # 384
```

If the model output is missing or the wrong shape, `vector=[]` and `vector_dim=0` are set rather than raising. Provenance confidence is fixed at `1.0`.

## Supported task types

- `embed`

## Supported domains

- `general`

## Usage example

```python
import time
from sentence_transformers import SentenceTransformer
from all_minilm_adapter import AllMiniLML6V2Adapter

model   = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
adapter = AllMiniLML6V2Adapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"sentences": ["The quick brown fox jumps over the lazy dog."]}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = model.encode(model_input["sentences"])
latency_ms = int((time.monotonic() - t0) * 1000)
# numpy.ndarray shape (1, 384)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access the embedding
vector = result_ir.payload.vector   # list[float], length 384
```

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
