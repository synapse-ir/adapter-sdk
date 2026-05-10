# whisper-large-v3 Adapter

Transcribes speech audio to text across 99 languages using openai/whisper-large-v3.

## Model details

| Field | Value |
|-------|-------|
| Model | openai/whisper-large-v3 |
| Task | transcribe |
| Domain | audio, multilingual |
| License | Apache 2.0 |

## Install

```bash
pip install synapse-adapter-sdk
pip install transformers torch
```

## Verified output schema

The transformers automatic-speech-recognition pipeline returns a single dict:

```python
from transformers import pipeline

pipe = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3")
result = pipe("audio.mp3")
# {"text": " And so my fellow Americans..."}
```

The adapter strips leading/trailing whitespace and sets `payload.content` to the transcription string, replacing the original audio reference. Provenance confidence is fixed at `1.0`.

## Audio input formats

`payload.content` carries the audio input. The transformers pipeline accepts:

| Format | Example |
|--------|---------|
| File path string | `"/data/earnings_call.mp3"` |
| NumPy float32 array at 16 kHz | `np.array([...], dtype=np.float32)` |
| Dict with array and sampling rate | `{"array": np.ndarray, "sampling_rate": 16000}` |

Common audio formats supported: MP3, WAV, FLAC, OGG, M4A.

## Supported task types

- `transcribe`

## Supported domains

- `audio`
- `multilingual`

## Usage example

```python
import time
from transformers import pipeline
from whisper_large_v3_adapter import WhisperLargeV3Adapter

pipe    = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3")
adapter = WhisperLargeV3Adapter()

# 1. Prepare model input — payload.content holds the audio reference
model_input = adapter.ingress(ir)
# {"audio": "/data/earnings_call.mp3"}

# 2. Run the model (caller's responsibility)
t0 = time.monotonic()
model_output = pipe(model_input["audio"])
latency_ms = int((time.monotonic() - t0) * 1000)
# {"text": " Good morning. Revenue for Q3 came in at..."}

# 3. Convert output back to canonical IR
result_ir = adapter.egress(model_output, ir, latency_ms=latency_ms)

# 4. Access the transcription — original audio reference is REPLACED
transcript = result_ir.payload.content
# "Good morning. Revenue for Q3 came in at..."
```

Whisper large-v3 automatically detects the spoken language — no language tag is required in the IR. To force a specific language or enable translation to English, pass `generate_kwargs` to the pipeline (caller's responsibility, outside the adapter contract).

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
