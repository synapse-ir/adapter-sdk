# Docling Adapter

Converts PDF, DOCX, PPTX, HTML, and other document formats into structured markdown with typed text block entities.

## Model details

| Field | Value |
|-------|-------|
| Model | docling-project/docling |
| Task | extract |
| Domain | document, general |
| License | MIT |

## Install

```bash
pip install synapse-adapter-sdk
pip install docling
```

## Verified output schema

The adapter maps `DoclingDocument` output as follows:

- `payload.content` — full document as markdown string (from `export_to_markdown()`)
- `payload.entities` — one `Entity` per text block with `label` set to the block's semantic type
- `payload.data["docling_table_count"]` — number of tables found (when > 0)
- `payload.data["docling_page_count"]` — number of pages found (when > 0)

Example `payload.data`:

```json
{
  "docling_table_count": 3,
  "docling_page_count": 12
}
```

Provenance confidence is fixed at `1.0` — Docling produces a complete result or raises an exception.

## Supported task types

- `extract`

## Supported domains

- `document`
- `general`

## Usage example

```python
import time
from docling.document_converter import DocumentConverter
from docling_adapter import DoclingAdapter

converter = DocumentConverter()
adapter   = DoclingAdapter()

# 1. Prepare model input — payload.content holds a file path or URL
model_input = adapter.ingress(ir)
# {"source": "/data/contract.pdf"}

# 2. Run Docling (caller's responsibility)
t0 = time.monotonic()
result = converter.convert(model_input["source"])
latency_ms = int((time.monotonic() - t0) * 1000)

# 3. Convert output back to canonical IR
result_ir = adapter.egress(result.document, ir, latency_ms=latency_ms)

# 4. Access results
markdown = result_ir.payload.content
entities = result_ir.payload.entities  # list of text blocks
table_count = result_ir.payload.data.get("docling_table_count", 0)
```

The adapter also accepts the dict produced by `DoclingDocument.export_to_dict()` as a fallback when a live `DoclingDocument` is not available.

## Source

[github.com/synapse-ir/adapters](https://github.com/synapse-ir/adapters)
