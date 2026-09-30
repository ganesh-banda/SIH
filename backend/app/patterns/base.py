"""Pattern detector interface.

Detectors return EVIDENCE, not just a boolean: every result says what was
measured, on which nodes, so the explanation layer can describe it exactly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from app.graph.graph_builder import TransactionGraph


@dataclass
class PatternResult:
    pattern: str                      # e.g. "peeling_chain"
    subject: str                      # node id the result is about
    detected: bool
    score: float | None = None        # optional detector score (not a risk %)
    evidence: dict[str, Any] = field(default_factory=dict)
    related_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PatternDetector(Protocol):
    name: str

    def detect(self, graph: TransactionGraph) -> list[PatternResult]: ...
