# clip-vit-base-patch32 Adapter

Zero-shot image classifier that ranks any set of natural-language candidate labels against an image using openai/clip-vit-base-patch32.

## Model details

| Field | Value |
|-------|-------|
| Model | openai/clip-vit-base-patch32 |
| Task | classify |
| Domain | multimodal, vision |
| License | MIT |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers zero-shot-image-classification pipeline returns a list of dicts sorted by descending score, one per candidate label:

```python
from transformers import pipeline

clip = pipeline("zero-shot-image-classification", model="openai/clip-vit-base-patch32")
result = clip(
    "http://images.cocodataset.org/val2017/000000039769.jpg",
    candidate_labels=["a photo of a cat", "a photo of a dog", "a photo of a car"],
)
# [
#   {'score': 0.9993917942047119, 'label': 'a photo of a cat'},
#   {'score': 0.0003519294841680676, 'label': 'a photo of a dog'},
#   {'score': 0.0002562698791734874, 'label': 'a photo of a car'},
# ]
```

The adapter stores **all** labels in `payload.labels` as `Classification` objects sorted by descending score. Provenance confidence equals `result[0].score`.

## Image input and candidate labels

The image and labels are split across two IR fields:

- **`payload.content`** — the image input (file path string, URL, or PIL Image object)
- **`task_header.candidate_labels`** — the text candidate labels to rank against the image

```python
from synapse_sdk.types import TaskHeader

task_header = TaskHeader(
    task_type="classify",
    domain="general",
    priority=2,
    latency_budget_ms=5000,
    candidate_labels=["a photo of a cat", "a photo of a dog", "a photo of a car"],
)
```

If `candidate_labels` is `None` or empty, the adapter falls back to the default label set: `["object", "animal", "vehicle", "person", "food"]`.

## Supported task types

- `classify`

## Supported domains

- `multimodal`
- `vision`

## Usage example

```python
import time
from transformers import pipeline
from clip_vit_base_patch32_adapter import ClipVitBasePatch32Adapter

clip    = pipeline("zero-shot-image-classification", model="openai/clip-vit-base-patch32")
adapter = ClipVitBasePatch32Adapter()

# 1. Prepare model input
#    payload.content = image path/URL; task_header.candidate_labels = label list
model_input = adapter.ingress(ir)
# {"image": "http://...", "candidate_labels": ["a photo of a cat", ...]}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = clip(**model_input)
latency_ms = int((time.monotonic() - t0) * 1000)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access ranked results
top = result_ir.payload.labels[0]
print(top.label, top.score)   # "a photo of a cat"  0.9994
```

CLIP jointly embeds images and text into a shared 512-dimensional space using contrastive learning on 400 million image-text pairs. Zero-shot classification requires no fine-tuning — any descriptive label vocabulary works at inference time.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
