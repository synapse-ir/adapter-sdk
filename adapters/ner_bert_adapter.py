"""NERBertAdapter — wraps dslim/bert-base-NER for the SYNAPSE pipeline."""

from __future__ import annotations

import time
from typing import Any

from synapse_sdk.types import (
    CanonicalIR,
    ComplianceEnvelope,
    Entity,
    Payload,
    ProvenanceEntry,
)


class NERBertAdapter:
    MODEL_ID = "dslim/bert-base-NER"
    ADAPTER_VERSION = "1.0.0"

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        result: dict[str, Any] = {"text": ir.payload.content or ""}
        if ir.task_header.quality_floor is not None:
            result["threshold"] = ir.task_header.quality_floor
        return result

    def egress(
        self,
        model_output: Any,
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        entities: list[dict[str, Any]] = model_output if isinstance(model_output, list) else []

        mapped: list[Entity] = [
            Entity(
                text=e["word"],
                label=e["entity"],
                confidence=float(e["score"]),
                start=e.get("start"),
                end=e.get("end"),
            )
            for e in entities
        ]

        confidence = (sum(float(e["score"]) for e in entities) / len(entities)) if entities else 0.0

        pii_detected = any("PER" in e["entity"] for e in entities)
        if pii_detected:
            old = original_ir.compliance_envelope
            compliance = ComplianceEnvelope(
                pii_present=True,
                required_tags=old.required_tags,
                data_residency=old.data_residency,
                retention_policy=old.retention_policy,
                purpose_limitation=old.purpose_limitation,
            )
        else:
            compliance = original_ir.compliance_envelope

        new_entry = ProvenanceEntry(
            model_id=self.MODEL_ID,
            adapter_version=self.ADAPTER_VERSION,
            confidence=round(confidence, 6),
            latency_ms=latency_ms,
            timestamp_unix=int(time.time()),
        )
        provenance = [*original_ir.provenance, new_entry]

        return CanonicalIR(
            ir_version=original_ir.ir_version,
            message_id=original_ir.message_id,
            task_header=original_ir.task_header,
            payload=Payload(
                modality=original_ir.payload.modality,
                content=original_ir.payload.content,
                entities=mapped if mapped else None,
                vector=original_ir.payload.vector,
                data=original_ir.payload.data,
                binary_b64=original_ir.payload.binary_b64,
                language=original_ir.payload.language,
                schema_ref=original_ir.payload.schema_ref,
                context_ref=original_ir.payload.context_ref,
                embedding_model=original_ir.payload.embedding_model,
                mime_type=original_ir.payload.mime_type,
            ),
            provenance=provenance,
            compliance_envelope=compliance,
        )
