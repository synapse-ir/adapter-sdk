# bart-large-mnli Adapter

Zero-shot text classifier that classifies input against any caller-supplied labels via Natural Language Inference using facebook/bart-large-mnli.

## Model details

| Field | Value |
|-------|-------|
| Model | facebook/bart-large-mnli |
| Task | classify |
| Domain | general |
| License | MIT |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers zero-shot-classification pipeline returns all candidate labels sorted by descending probability:

```python
from transformers import pipeline

classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
result = classifier(
    "This earnings call showed record growth.",
    candidate_labels=["positive", "negative", "neutral"],
)
# {
#   "sequence": "This earnings call showed record growth.",
#   "labels":   ["positive", "neutral", "negative"],
#   "scores":   [0.8912, 0.0721, 0.0367]
# }
```

The adapter maps **all** labels to `payload.labels` as `Classification` objects sorted by descending score:

```python
result_ir.payload.labels[0].label  # top-ranked label
result_ir.payload.labels[0].score  # its probability
```

Provenance confidence equals `scores[0]` — the top label's probability.

## Candidate labels

Labels are read from `ir.task_header.candidate_labels` at inference time. Any list of strings is valid — domain names, intent categories, topic tags, etc. When no labels are provided the adapter defaults to `["positive", "negative", "neutral"]`.

```python
from synapse_sdk.types import TaskHeader

task_header = TaskHeader(
    task_type="classify",
    domain="general",
    priority=2,
    latency_budget_ms=5000,
    candidate_labels=["sports", "politics", "technology", "finance"],
)
```

Unlike single-label classifiers, the full ranked probability distribution over **all** candidate labels is preserved in `payload.labels` — callers can inspect more than just the top prediction.

## Supported task types

- `classify`

## Supported domains

- `general`

## Usage example

```python
import time
from transformers import pipeline
from bart_large_mnli_adapter import BartLargeMnliAdapter

classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
adapter    = BartLargeMnliAdapter()

# 1. Prepare model input — candidate_labels come from task_header
model_input = adapter.ingress(ir)
# {"text": "...", "candidate_labels": ["sports", "politics", "technology"]}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = classifier(
    model_input["text"],
    candidate_labels=model_input["candidate_labels"],
)
latency_ms = int((time.monotonic() - t0) * 1000)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access ranked results
for classification in result_ir.payload.labels:
    print(classification.label, classification.score)
```

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
