"""Convert pattern-detector results into evidence items."""

from __future__ import annotations

from app.explainability.evidence_builder import EvidenceItem, EvidenceKind
from app.patterns.base import PatternResult


def pattern_to_evidence(result: PatternResult) -> EvidenceItem | None:
    """Only *detected* patterns become evidence."""
    if not result.detected:
        return None
    values = dict(result.evidence)
    if result.score is not None:
        values.setdefault("score", result.score)
    return EvidenceItem(kind=EvidenceKind.PATTERN, type=result.pattern, values=values,
                        source=f"pattern:{result.pattern}")
