"""Turn an EvidenceBundle into investigator-readable text. No LLM.

Rules:
* one sentence per evidence item that has a registered template,
* items with no template, or whose template lacks the values it needs, are
  skipped and reported in ``unexplained``, never paraphrased or guessed,
* every sentence keeps a pointer to the evidence item it came from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.explainability.evidence_builder import EvidenceBundle
from app.explainability.templates import TEMPLATES, Template

logger = logging.getLogger(__name__)


@dataclass
class Explanation:
    subject: str
    summary: str | None
    sentences: list[dict] = field(default_factory=list)   # {"text", "evidence_index"}
    unexplained: list[dict] = field(default_factory=list)  # {"evidence_index", "type", "reason"}

    @property
    def text(self) -> str:
        parts = ([self.summary] if self.summary else []) + [s["text"] for s in self.sentences]
        return "\n\n".join(parts)


def generate_explanation(bundle: EvidenceBundle,
                         templates: dict[str, Template] | None = None) -> Explanation:
    registry = TEMPLATES if templates is None else templates
    summary = None
    if bundle.final_risk is not None:
        summary = f"{bundle.subject} received a risk score of {bundle.final_risk:.0f}/100."

    explanation = Explanation(subject=bundle.subject, summary=summary)
    for index, item in enumerate(bundle.items):
        template = registry.get(item.type)
        if template is None:
            explanation.unexplained.append(
                {"evidence_index": index, "type": item.type, "reason": "no template"})
            continue
        text = template(item.values)
        if not text:
            explanation.unexplained.append(
                {"evidence_index": index, "type": item.type, "reason": "missing values"})
            continue
        explanation.sentences.append({"text": text, "evidence_index": index})

    if explanation.unexplained:
        logger.debug("%d evidence items had no rendered sentence", len(explanation.unexplained))
    return explanation
