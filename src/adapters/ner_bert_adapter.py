"""SYNAPSE adapter for dslim/bert-base-NER (§2.1, §2.2, G-S04)."""

from __future__ import annotations

from typing import Any

from synapse_sdk.base import AdapterBase
from synapse_sdk.types import CanonicalIR, ComplianceEnvelope, Entity


class NERBertAdapter(AdapterBase):
    """
    Adapter for dslim/bert-base-NER.

    Transforms canonical IR to the model's pipeline input format (ingress)
    and converts the token-level entity list back to canonical IR (egress).

    Supported entity types: PER, ORG, LOC, MISC (with B-/I- BIO prefixes).
    G-S04: upgrades compliance_envelope.pii_present to True when any PER
    entity is present in the model output.
    """

    MODEL_ID = "dslim/bert-base-NER"
    ADAPTER_VERSION = "1.0.0"

    # ------------------------------------------------------------------
    # ingress
    # ------------------------------------------------------------------

    def ingress(self, ir: CanonicalIR) -> dict[str, Any]:
        result: dict[str, Any] = {"text": ir.payload.content or ""}
        if ir.task_header.quality_floor is not None:
            result["threshold"] = ir.task_header.quality_floor
        return result

    # ------------------------------------------------------------------
    # egress
    # ------------------------------------------------------------------

    def egress(
        self,
        model_output: Any,
        original_ir: CanonicalIR,
        latency_ms: int,
    ) -> CanonicalIR:
        raw: list[dict[str, Any]] = (
            model_output if isinstance(model_output, list) else []
        )

        entities: list[Entity] = []
        scores: list[float] = []
        has_person = False

        for item in raw:
            label = str(item.get("entity", ""))
            text = str(item.get("word", ""))
            score = float(item.get("score", 0.0))
            start = item.get("start")
            end = item.get("end")

            scores.append(score)
            entities.append(
                Entity(
                    text=text,
                    label=label,
                    start=start,
                    end=end,
                    confidence=score,
                )
            )

            if "PER" in label:
                has_person = True

        confidence = sum(scores) / len(scores) if scores else 0.0

        updated = original_ir.clone()

        # Populate entities on the payload (does not touch content).
        if entities:
            updated.payload.entities = entities

        # G-S04: upgrade pii_present when a PERSON entity is detected.
        if has_person and not updated.compliance_envelope.pii_present:
            orig = original_ir.compliance_envelope
            updated.compliance_envelope = ComplianceEnvelope(
                required_tags=orig.required_tags,
                pii_present=True,
                data_residency=orig.data_residency,
                retention_policy=orig.retention_policy,
                purpose_limitation=orig.purpose_limitation,
            )

        updated.provenance.append(
            self.build_provenance(confidence=confidence, latency_ms=latency_ms)
        )

        return updated
