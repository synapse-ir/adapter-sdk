# OpenAI Classifier Adapter

Zero-shot text classifier backed by GPT-4o-mini that classifies input into caller-supplied labels.

## Model details

| Field | Value |
|-------|-------|
| Model | openai/gpt-4o-mini |
| Task | classify |
| Domain | general |
| License | MIT |

## Install

```bash
npm install openai
```

The adapter is written in TypeScript and ships as part of the SYNAPSE adapter SDK.

## Verified output schema

The adapter calls the OpenAI chat completions endpoint in JSON mode and expects:

```json
{"label": "chosen label", "confidence": 0.92}
```

The adapter stores the parsed result in `payload.data`:

```json
{
  "label": "positive",
  "confidence": 0.92,
  "token_count": 45
}
```

Cost is estimated from token usage at current gpt-4o-mini list pricing
(input: $0.15/M tokens, output: $0.60/M tokens) and recorded in provenance `cost_usd`.

## Supported task types

- `classify`

## Supported domains

- `general`

## Usage example

```typescript
import OpenAI from "openai";
import { OpenAIClassifierAdapter } from "./openai-classifier";

const client = new OpenAI();
const adapter = new OpenAIClassifierAdapter(client, ["positive", "negative", "neutral"]);

// ingress builds the JSON-mode chat request
const modelInput = adapter.ingress(ir);

// caller drives inference
const t0 = Date.now();
const modelOutput = await client.chat.completions.create(modelInput);
const latencyMs = Date.now() - t0;

// egress parses {label, confidence} and writes into payload.data
const resultIr = adapter.egress(modelOutput, ir, latencyMs);

const label = resultIr.payload.data?.label;        // "positive"
const confidence = resultIr.payload.data?.confidence; // 0.92
```

The `labels` array is passed to the constructor and injected into the system prompt at ingress time. Any set of string labels is valid.

## PII handling

This adapter does not extract person entities. `compliance_envelope.pii_present` is propagated from the input IR when set but is never upgraded to `true` by this adapter.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
