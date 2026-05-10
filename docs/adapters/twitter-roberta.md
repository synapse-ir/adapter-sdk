# twitter-roberta-sentiment Adapter

Social media sentiment classifier (Negative / Neutral / Positive) using cardiffnlp/twitter-roberta-base-sentiment-latest.

## Model details

| Field | Value |
|-------|-------|
| Model | cardiffnlp/twitter-roberta-base-sentiment-latest |
| Task | classify |
| Domain | conversational |
| License | CC BY 4.0 (attribution required) |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers sentiment-analysis pipeline returns a top-1 list:

```python
from transformers import pipeline

pipe = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest",
)
result = pipe("I love this product!")
# [{'label': 'Positive', 'score': 0.9743}]
```

The adapter maps this to `payload.labels`:

```python
result_ir.payload.labels[0].label  # 'Negative' | 'Neutral' | 'Positive'
result_ir.payload.labels[0].score  # float in [0.0, 1.0]
```

!!! note "Title-cased labels"
    Labels are **title-cased**: `'Negative'`, `'Neutral'`, `'Positive'`. This differs from
    other sentiment models (e.g. FinBERT) that return lowercase labels. Callers that switch
    between adapters must account for this when matching labels programmatically.

## Supported task types

- `classify`

## Supported domains

- `conversational`

## Usage example

```python
import time
from transformers import pipeline
from twitter_roberta_sentiment_adapter import TwitterRobertaSentimentAdapter

pipe = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest",
)
adapter = TwitterRobertaSentimentAdapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"text": "I love this product!"}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = pipe(model_input["text"])
latency_ms = int((time.monotonic() - t0) * 1000)
# [{"label": "Positive", "score": 0.9743}]

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access results
label = result_ir.payload.labels[0].label  # 'Positive'
score = result_ir.payload.labels[0].score  # 0.9743
```

The model is fine-tuned on 124 million tweets (Jan 2018 – Dec 2021) and generalises well to Reddit, product reviews, and other user-generated content. It degrades on formal or domain-specific prose (legal, medical, financial).

## PII handling

Sentiment classification does not extract person entities. `compliance_envelope.pii_present` is never upgraded to `True` by this adapter.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
