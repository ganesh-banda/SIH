"""Graph risk propagation (Personalized PageRank / Random Walk with Restart).

Requires known risky seed wallets/entities from the dataset. Proximity to a
seed is ONE signal, never proof. TODO(dataset): only if seeds exist.
"""

from __future__ import annotations

from app.graph.graph_builder import TransactionGraph


def propagate_risk(graph: TransactionGraph, seeds: dict[str, float], **params) -> dict[str, float]:
    raise NotImplementedError("Pending dataset: need known risky seeds.")
