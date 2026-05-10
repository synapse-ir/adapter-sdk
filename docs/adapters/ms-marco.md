# ms-marco-MiniLM-L6-v2 Adapter

Scores passage relevance against a query for RAG reranking pipelines using cross-encoder/ms-marco-MiniLM-L6-v2.

## Model details

| Field | Value |
|-------|-------|
| Model | cross-encoder/ms-marco-MiniLM-L6-v2 |
| Task | rank |
| Domain | general |
| License | Apache 2.0 |

## Install

```bash
pip install synapse-adapter-sdk
pip install sentence-transformers torch
```

## Verified output schema

`CrossEncoder.predict()` returns a raw logit as a `numpy.ndarray` of shape `(1,)`:

```python
from sentence_transformers import CrossEncoder

model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")
scores = model.predict([("How many people live in Berlin?",
                          "Berlin had a population of 3.7 million in 2022.")])
# numpy.ndarray([8.607138], dtype=float32)
```

The adapter normalises the raw logit to `[0.0, 1.0]` using the sigmoid function and stores it in `payload.score`.

## Sigmoid normalization

The raw logit is unbounded (typically in the range −10 to +10). A sigmoid transform maps it to a principled probability-like score:

```
score = 1 / (1 + exp(-raw_score))
```

- A raw score of `0` maps to exactly `0.5` (model is neutral)
- Positive logits map above `0.5` (relevant passage)
- Negative logits map below `0.5` (not relevant)

## Supported task types

- `rank`

## Supported domains

- `general`

## Usage example

```python
import time
from sentence_transformers import CrossEncoder
from ms_marco_cross_encoder_adapter import MsMarcoCrossEncoderAdapter

model   = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")
adapter = MsMarcoCrossEncoderAdapter()

# 1. Prepare model input
#    task_header.query holds the query; payload.content holds the passage
model_input = adapter.ingress(ir)
# {"query": "How many people live in Berlin?",
#  "passage": "Berlin had a population of 3.7 million in 2022."}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
scores = model.predict([(model_input["query"], model_input["passage"])])
latency_ms = int((time.monotonic() - t0) * 1000)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(scores, ir, latency_ms=latency_ms)

# 4. Access the relevance score in [0.0, 1.0]
relevance = result_ir.payload.score
```

The query is read from `ir.task_header.query`. Set this field when building the IR for ranking:

```python
from synapse_sdk.types import TaskHeader

task_header = TaskHeader(
    task_type="rank",
    domain="general",
    query="How many people live in Berlin?",
)
```

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
