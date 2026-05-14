# Canonical IR

The central data structure of the SYNAPSE ecosystem. Every model receives a `CanonicalIR` and every adapter must return one.

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

All six fields are required. `provenance` and `compliance_envelope` default to `[]` and `{}` respectively.

---

## CanonicalIR fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ir_version` | `str` | yes | Semver string, e.g. `"1.0.0"` |
| `message_id` | `str` | yes | UUID v4 identifying this IR instance |
| `task_header` | `TaskHeader` | yes | Routing and scheduling metadata |
| `payload` | `Payload` | yes | The data being processed |
| `provenance` | `list[ProvenanceEntry]` | no | Append-only audit chain, default `[]` |
| `compliance_envelope` | `ComplianceEnvelope` | no | PII and data governance flags, default `{}` |

### Methods

```python
ir.clone()          # Deep copy — no shared state. Use this in egress().
ir.copy()           # Shallow copy — shared sub-objects. Avoid in adapters.
ir.to_json()        # Serialize to compact JSON string.
CanonicalIR.from_json(data)  # Deserialize from JSON string or bytes.
```

Always use `clone()` in `egress()`. `copy()` shares the provenance list, which means appending to the clone also appends to the original.

---

## TaskHeader

Routing and execution metadata. Carried unchanged through every pipeline hop.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_type` | `TaskType` | yes | What kind of task this is |
| `domain` | `Domain` | yes | Subject-matter domain |
| `priority` | `int` | yes | `1` (low) to `3` (high) |
| `latency_budget_ms` | `int` | yes | Maximum acceptable end-to-end latency |
| `cost_ceiling` | `float \| None` | no | Maximum acceptable cost in USD |
| `quality_floor` | `float \| None` | no | Minimum acceptable confidence, `[0.0, 1.0]` |
| `session_id` | `str \| None` | no | Groups related pipeline calls |
| `idempotency_key` | `str \| None` | no | Deduplication key |
| `query` | `str \| None` | no | Query string for `rank` adapters |
| `candidate_labels` | `list[str] \| None` | no | Labels for zero-shot classification |
| `failure_policy` | `FailurePolicy` | no | Pipeline failure semantics, default `"abort"` |
| `trace_context` | `TraceContext \| None` | no | W3C Trace Context for distributed tracing |

### TaskType values

`classify` `extract` `generate` `summarize` `embed` `rank` `validate` `translate` `score` `transcribe`

### Domain values

`general` `legal` `medical` `finance` `code` `scientific` `multilingual` `conversational` `audio` `document` `multimodal` `vision`

### FailurePolicy values

| Value | Behaviour |
|-------|-----------|
| `abort` | Any stage failure aborts the entire pipeline (default) |
| `partial` | Failed stages are skipped; returns `PartialCompletionResponse` |
| `fallback` | Tries a fallback model before falling back to `partial` |

---

## Payload

Carries the data being processed. The `modality` field determines which fields are required.

| Field | Type | Modality | Description |
|-------|------|----------|-------------|
| `modality` | `str` | all | `"text"` `"embedding"` `"structured"` `"binary"` |
| `content` | `str \| None` | text (required) | Input text |
| `content_length` | `int \| None` | text | Character count |
| `language` | `str \| None` | text | BCP-47 language tag |
| `vector` | `list[float] \| None` | embedding (required) | Embedding vector |
| `vector_dim` | `int \| None` | embedding | Vector dimensionality |
| `embedding_model` | `str \| None` | embedding | Model that produced the vector |
| `data` | `dict \| None` | structured (required) | Arbitrary structured data |
| `schema_ref` | `str \| None` | structured | URI of the data schema |
| `binary_b64` | `str \| None` | binary (required) | Base64-encoded binary |
| `mime_type` | `str \| None` | binary (required) | MIME type of the binary |
| `byte_length` | `int \| None` | binary | Decoded byte count |
| `context_ref` | `str \| None` | all | Context store key for large off-payload data |
| `entities` | `list[Entity] \| None` | all | NER/extraction results |
| `labels` | `list[Classification] \| None` | all | Classification results |
| `score` | `float \| None` | all | Relevance score for `rank` adapters, `[0.0, 1.0]` |

### Size limits

| Field | Soft limit | Hard limit |
|-------|-----------|------------|
| `content` | 1 MB | 10 MB |
| `vector` | 10 MB | 50 MB |
| `data` | 500 KB | 5 MB |
| `binary_b64` | 10 MB | 50 MB |
| Total IR | 20 MB | 100 MB |

Exceeding a soft limit logs a warning. Exceeding a hard limit raises `IRPayloadTooLargeError`. Use `context_ref` for large payloads.

---

## ProvenanceEntry

Appended by each adapter's `egress()`. **Immutable** — any attempt to modify a field raises `TypeError`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | `str` | yes | Registry identifier of the model |
| `adapter_version` | `str` | yes | Semver of the adapter |
| `confidence` | `float` | yes | Model confidence, `[0.0, 1.0]` |
| `latency_ms` | `int` | yes | Wall-clock time for this hop, `>= 0` |
| `timestamp_unix` | `int` | yes | Unix timestamp when egress ran |
| `cost_usd` | `float \| None` | no | Inference cost in USD |
| `token_count` | `int \| None` | no | Tokens consumed |
| `warnings` | `list[str] \| None` | no | Non-fatal advisory messages |
| `branch_id` | `str \| None` | no | UUID linking entries in a parallel branch (G-S03) |
| `branch_role` | `BranchRole \| None` | no | Role in a parallel pipeline |

### BranchRole values (G-S03)

| Value | Meaning |
|-------|---------|
| `source` | Stage that initiated the fan-out |
| `branch` | A parallel branch stage |
| `merge` | Stage that aggregated branch results |

Sequential pipelines leave `branch_id` and `branch_role` absent.

---

## ComplianceEnvelope

Carries data governance flags. Must be propagated unchanged through every pipeline hop.

| Field | Type | Description |
|-------|------|-------------|
| `required_tags` | `list[str] \| None` | Data governance tags that must be present |
| `pii_present` | `bool \| None` | Whether the payload contains PII |
| `data_residency` | `list[str] \| None` | Region codes where data may be processed |
| `retention_policy` | `str \| None` | Retention policy identifier |
| `purpose_limitation` | `str \| None` | Permitted processing purposes |

---

## Entity

Used in `payload.entities` for NER and extraction adapters.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `str` | yes | The entity text |
| `label` | `str` | yes | Entity type (e.g. `"PERSON"`, `"ORG"`) |
| `start` | `int \| None` | no | Character offset start |
| `end` | `int \| None` | no | Character offset end |
| `confidence` | `float \| None` | no | Entity confidence, `[0.0, 1.0]` |

---

## Classification

Used in `payload.labels` for classification and zero-shot adapters.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | `str` | yes | The predicted label |
| `score` | `float` | yes | Softmax confidence, `[0.0, 1.0]` |

```python
from synapse_sdk.types import Classification

updated.payload.labels = [
    Classification(label="positive", score=0.94),
    Classification(label="neutral",  score=0.05),
]
```

---

## TraceContext (G-S01)

W3C Trace Context propagated through the IR for distributed tracing. Optional — when absent, `propagate_trace_context()` synthesises a new root trace.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `traceparent` | `str` | yes | W3C traceparent: `00-{trace_id}-{parent_id}-{flags}` |
| `tracestate` | `str \| None` | no | Vendor-specific trace state |

```python
from synapse_sdk import propagate_trace_context, adapter_span

# Propagate existing trace or start a new one
ir = propagate_trace_context(ir)

# Instrument an adapter call
with adapter_span(ir, adapter) as ir_with_trace:
    result = adapter.egress(output, ir_with_trace, latency_ms=43)
```

---

## Partial pipeline failure types (G-S02)

When `task_header.failure_policy = "partial"`, a failed stage is skipped and the pipeline returns a `PartialCompletionResponse` instead of raising.

### FailedStage

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | `str` | yes | Model that failed |
| `error` | `str` | yes | Error class name |
| `detail` | `str \| None` | no | Human-readable error detail |
| `stage_index` | `int \| None` | no | Position in the pipeline |

### PartialCompletionResponse

| Field | Type | Description |
|-------|------|-------------|
| `partial_completion` | `bool` | Always `True` |
| `completed_stages` | `list[str]` | `model_id` values that succeeded |
| `failed_stages` | `list[FailedStage]` | Records of each failure |
| `payload` | `Payload` | Best available result from completed stages |
| `provenance` | `list[ProvenanceEntry]` | Entries from completed stages only |

---

## Error types

| Error | Raised when |
|-------|-------------|
| `IRPayloadTooLargeError` | A payload field exceeds its hard size limit |
| `IRInvalidFieldError` | A string field contains a forbidden value (e.g. null byte) |

Both serialise to a JSON G-C06 error envelope accessible via `error.envelope`.

---

Full specification: [github.com/synapse-ir/spec](https://github.com/synapse-ir/spec)
