# Canonical IR

The central data structure of the SYNAPSE ecosystem.

## Top-level structure


```json
{
  "ir_version": "1.0.0",
  "message_id": "019123ab-dead-7f00-beef-cafe0000a001",
  "task_header": { },
  "payload": { },
  "provenance": [],
  "compliance_envelope": { }
}
```



All six fields are required.

## TaskHeader

### Valid task_type values

`classify` `extract` `generate` `summarize` `embed` `rank` `validate`
`translate` `score`

### Valid domain values

`general` `legal` `medical` `finance` `code` `scientific`
`multilingual` `conversational`

## Payload modalities

`text` `embedding` `structured` `binary`

## ProvenanceEntry

Appended by each model's egress adapter. Never modified.


```json
{
  "model_id": "ner-legal-v2.1",
  "adapter_version": "1.2.0",
  "confidence": 0.94,
  "latency_ms": 43,
  "timestamp_unix": 1746384021
}
```



Full specification: [github.com/synapse-ir/spec](https://github.com/synapse-ir/spec)
