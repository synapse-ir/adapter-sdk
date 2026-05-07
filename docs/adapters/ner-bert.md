# NER BERT Adapter

SYNAPSE adapter for [dslim/bert-base-NER](https://huggingface.co/dslim/bert-base-NER).

## Install


```bash
pip install synapse-adapter-sdk
pip install transformers torch
```


## Supported task types

- `extract`

## Supported domains

- `general`
- `legal`

## PII handling

When a PERSON entity is detected, the adapter automatically sets
`compliance_envelope.pii_present = True` and propagates this flag
through the pipeline. No application code required.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
