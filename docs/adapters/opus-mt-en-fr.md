# opus-mt-en-fr Adapter

Translates English text to French using Helsinki-NLP/opus-mt-en-fr (MarianMT seq2seq).

## Model details

| Field | Value |
|-------|-------|
| Model | Helsinki-NLP/opus-mt-en-fr |
| Task | translate |
| Domain | multilingual |
| License | Apache 2.0 |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch sentencepiece
```

## Verified output schema

The transformers translation pipeline returns exactly one dict:

```python
from transformers import pipeline

translator = pipeline("translation", model="Helsinki-NLP/opus-mt-en-fr")
result = translator("How are you?")
# [{'translation_text': 'Comment allez-vous ?'}]
```

The adapter sets `payload.content` to the translated string, replacing the source text.
Provenance confidence is fixed at `1.0` — seq2seq models produce a translation or raise.

## Supported task types

- `translate`

## Supported domains

- `multilingual`

## Usage example

```python
import time
from transformers import pipeline
from opus_mt_en_fr_adapter import OpusMtEnFrAdapter

translator = pipeline("translation", model="Helsinki-NLP/opus-mt-en-fr")
adapter    = OpusMtEnFrAdapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"text": "How are you?"}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = translator(model_input["text"])
latency_ms = int((time.monotonic() - t0) * 1000)
# [{"translation_text": "Comment allez-vous ?"}]

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access the translation — original content is REPLACED
french_text = result_ir.payload.content
```

## Pattern generality — all Helsinki-NLP opus-mt models

**This adapter pattern works for ALL `Helsinki-NLP/opus-mt-{src}-{tgt}` models** (1000+ language pairs). The transformers translation pipeline produces the same `[{"translation_text": str}]` output schema across the entire opus-mt family because all models share the MarianMT architecture.

To use a different language pair, copy this file and change only:

```python
MODEL_ID = "Helsinki-NLP/opus-mt-{src}-{tgt}"
```

The `ingress` and `egress` logic is **identical** for all pairs.

| Model ID | Direction |
|----------|-----------|
| `Helsinki-NLP/opus-mt-en-fr` | English → French (this adapter) |
| `Helsinki-NLP/opus-mt-en-de` | English → German |
| `Helsinki-NLP/opus-mt-en-es` | English → Spanish |
| `Helsinki-NLP/opus-mt-zh-en` | Chinese → English |
| `Helsinki-NLP/opus-mt-fr-en` | French → English |
| `Helsinki-NLP/opus-mt-en-ru` | English → Russian |

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
