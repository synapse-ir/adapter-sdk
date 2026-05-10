# BART Large CNN Adapter

Produces abstractive summaries of English-language text using facebook/bart-large-cnn.

## Model details

| Field | Value |
|-------|-------|
| Model | facebook/bart-large-cnn |
| Task | summarize |
| Domain | general |
| License | MIT |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers summarization pipeline returns:

```python
from transformers import pipeline

summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
result = summarizer("The tower is 324 metres (1,063 ft) tall...")
# [{"summary_text": "The tower is 324 metres tall..."}]
```

The adapter maps this to:

- `payload.content` — the generated summary string (replaces the source text)
- `payload.content_length` — character count of the summary

Provenance confidence is fixed at `1.0` — BART either produces a summary or raises.

!!! note "1024-token limit"
    BART's encoder accepts at most 1024 tokens (~3,000–4,000 characters of typical English text).
    Text exceeding this limit is silently truncated by the pipeline. Chunking is the caller's responsibility.

## Supported task types

- `summarize`

## Supported domains

- `general`

## Usage example

```python
import time
from transformers import pipeline
from bart_large_cnn_adapter import BartLargeCNNAdapter

summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
adapter    = BartLargeCNNAdapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"text": "...", "max_length": 130, "min_length": 30, "do_sample": False}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = summarizer(
    model_input["text"],
    max_length=model_input["max_length"],
    min_length=model_input["min_length"],
    do_sample=model_input["do_sample"],
)
latency_ms = int((time.monotonic() - t0) * 1000)
# [{"summary_text": "Generated summary here."}]

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access the summary — original content is REPLACED
summary = result_ir.payload.content
```

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
