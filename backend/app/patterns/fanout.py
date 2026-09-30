"""Pattern detector: fanout.

TODO(dataset): thresholds (chain length, forward ratio, time windows, ...)
are chosen from the real data's distributions, not guessed.
"""

from __future__ import annotations

from app.graph.graph_builder import TransactionGraph
from app.patterns.base import PatternResult


class Detector:
    name = "fanout"

    def detect(self, graph: TransactionGraph) -> list[PatternResult]:
        raise NotImplementedError("Pending dataset: fanout")
