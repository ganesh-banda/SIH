"""Structured evidence: the single source of truth for explanations.

Explanations are rendered ONLY from EvidenceItems. If something is not in the
evidence, it cannot appear in the explanation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EvidenceKind(str, Enum):
    MODEL = "model"            # SHAP contributions
    GRAPH = "graph"            # graph relationships / propagation
    PATTERN = "pattern"        # pattern detector output
    TRANSACTION = "transaction"
    ANOMALY = "anomaly"


@dataclass
class EvidenceItem:
    kind: EvidenceKind
    type: str                           # template key, e.g. "high_fan_out"
    values: dict[str, Any] = field(default_factory=dict)
    source: str | None = None           # which component produced it


@dataclass
class EvidenceBundle:
    subject: str                        # wallet / entity / transaction id
    final_risk: float | None = None
    risk_level: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    items: list[EvidenceItem] = field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
