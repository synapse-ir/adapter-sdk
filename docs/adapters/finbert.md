# FinBERT Adapter

Financial sentiment classifier that labels text as positive, negative, or neutral using ProsusAI/finbert.

## Model details

| Field | Value |
|-------|-------|
| Model | ProsusAI/finbert |
| Task | classify |
| Domain | finance |
| License | Apache 2.0 |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers sentiment-analysis pipeline returns a top-1 list:

```python
from transformers import pipeline

pipe = pipeline("sentiment-analysis", model="ProsusAI/finbert")
result = pipe("Revenues increased significantly this quarter.")
# [{'label': 'positive', 'score': 0.9723}]
```

The adapter maps this to `payload.labels`:

```python
result_ir.payload.labels[0].label  # "positive" | "negative" | "neutral"
result_ir.payload.labels[0].score  # float in [0.0, 1.0]
```

Labels are always **lowercase**. Provenance confidence equals the softmax score of the top class.

## Supported task types

- `classify`

## Supported domains

- `finance`

## Usage example

```python
import time
from transformers import pipeline
from finbert_adapter import FinbertAdapter

pipe    = pipeline("sentiment-analysis", model="ProsusAI/finbert")
adapter = FinbertAdapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"text": "The company reported record-breaking revenue this quarter."}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = pipe(model_input["text"])
latency_ms = int((time.monotonic() - t0) * 1000)
# [{"label": "positive", "score": 0.9712}]

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access results
label = result_ir.payload.labels[0].label   # "positive"
score = result_ir.payload.labels[0].score   # 0.9712
```

FinBERT labels reflect **market sentiment** expressed in the text, not the author's emotional tone:

- `positive` — optimism, growth, outperformance, or beats expectations
- `negative` — pessimism, decline, loss, or missed expectations
- `neutral` — factual, non-directional, or routine events

## PII handling

FinBERT classifies financial sentiment and does not extract person entities. `compliance_envelope.pii_present` is never upgraded to `True` by this adapter.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
