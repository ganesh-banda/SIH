"""Pattern detector: mixer_patterns.

TODO(dataset): thresholds (chain length, forward ratio, time windows, ...)
are chosen from the real data's distributions, not guessed.
"""

from __future__ import annotations

from app.graph.graph_builder import TransactionGraph
from app.patterns.base import PatternResult


class Detector:
    name = "mixer_patterns"

    def detect(self, graph: TransactionGraph) -> list[PatternResult]:
        raise NotImplementedError("Pending dataset: mixer_patterns")
