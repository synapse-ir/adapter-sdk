# JSL Clinical NER Adapter

Clinical named entity recognition for PROBLEM, TEST, and TREATMENT spans using John Snow Labs Spark NLP for Healthcare.

## Model details

| Field | Value |
|-------|-------|
| Model | johnsnowlabs/ner_clinical |
| Task | extract |
| Domain | medical |
| License | MIT (adapter) — requires John Snow Labs Healthcare NLP license |

## Install

```bash
pip install synapse-adapter-sdk
pip install johnsnowlabs
```

!!! warning "License required"
    The `ner_clinical` model requires a valid **John Snow Labs Healthcare NLP** license.
    The model weights are not open source. See [johnsnowlabs.com/spark-nlp-health](https://www.johnsnowlabs.com/spark-nlp-health/).

## Verified output schema

The Spark NLP `NerConverter` produces `Annotation` objects with:

```
annotation.result              # entity surface text (str)
annotation.begin               # character start offset (int)
annotation.end                 # character end offset (int)
annotation.metadata["entity"]  # "PROBLEM" | "TEST" | "TREATMENT"
annotation.metadata["confidence"]  # confidence score as string, e.g. "0.9871"
```

The adapter maps these to `payload.entities`:

```json
[
  {"text": "chest pain", "label": "PROBLEM", "start": 12, "end": 21, "confidence": 0.987},
  {"text": "ECG",        "label": "TEST",    "start": 36, "end": 38, "confidence": 0.995},
  {"text": "aspirin",    "label": "TREATMENT","start": 53, "end": 59, "confidence": 0.981}
]
```

## Supported task types

- `extract`

## Supported domains

- `medical`

## Usage example

```python
import time
from ner_clinical_adapter import NerClinicalAdapter

adapter = NerClinicalAdapter()

# 1. Prepare model input
model_input = adapter.ingress(ir)
# {"text": "Patient presented with chest pain. ECG ordered. Aspirin prescribed."}

# 2. Run the Spark NLP pipeline (caller's responsibility)
t0 = time.monotonic()
spark_result = spark_pipeline.transform(spark_df_from(model_input))
ner_chunks = ner_chunks_from(spark_result)
latency_ms = int((time.monotonic() - t0) * 1000)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(ner_chunks, ir, latency_ms=latency_ms)

# 4. Access entities
for entity in result_ir.payload.entities:
    print(entity.label, entity.text, entity.confidence)
```

The adapter follows the SYNAPSE pure-function contract. The caller owns the Spark session and pipeline.

## PII handling

When `PROBLEM` entities are extracted (which may contain patient-identifying information), the adapter automatically sets `compliance_envelope.pii_present = True` per SYNAPSE rule G-S04. This flag is also propagated when it is already `True` on the incoming IR.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
