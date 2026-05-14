# ClinicalBERT Adapter

Clinical masked language model that predicts masked tokens in clinical text using medicalai/ClinicalBERT.

## Model details

| Field | Value |
|-------|-------|
| Model | medicalai/ClinicalBERT |
| Task | classify |
| Domain | medical |
| License | See [model card](https://huggingface.co/medicalai/ClinicalBERT) |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers fill-mask pipeline returns a ranked list of candidates:

```python
from transformers import pipeline

pipe = pipeline("fill-mask", model="medicalai/ClinicalBERT")
result = pipe("The patient reports chest [MASK] after exercise.")
# [{'token_str': 'pain', 'score': 0.8498, 'sequence': '...', 'token': 38576}]
```

The adapter maps each candidate to `payload.labels`:

```python
result_ir.payload.labels[0].label  # "pain"
result_ir.payload.labels[0].score  # float in [0.0, 1.0]
```

Candidates are returned in model order. Empty or malformed outputs produce `payload.labels == []` and provenance confidence `0.0`.

## Supported task types

- `classify`

## Supported domains

- `medical`

## Usage example

```python
import time
from transformers import pipeline
from clinicalbert.clinicalbert_adapter import ClinicalBertAdapter

pipe    = pipeline("fill-mask", model="medicalai/ClinicalBERT")
adapter = ClinicalBertAdapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"text": "The patient reports chest [MASK] after exercise."}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = pipe(model_input["text"])
latency_ms = int((time.monotonic() - t0) * 1000)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access results
label = result_ir.payload.labels[0].label  # "pain"
score = result_ir.payload.labels[0].score  # 0.8498
```

## PHI handling

Clinical text may contain PHI or PII. This adapter does not inspect content, does not extract entities, and does not set `compliance_envelope.pii_present = True`. De-identification is the caller's responsibility.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
