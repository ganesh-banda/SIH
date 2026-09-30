"""Entity clustering (INTERFACE ONLY - not implemented yet).

Goal: group wallets that MAY be controlled by the same entity. Results are
always inferences with a confidence and supporting evidence, never proof of
ownership.

Candidate signals (PS-5 mentions common-input-ownership + graph embeddings):
common-input heuristic, co-occurrence, temporal similarity, shared network
metadata. Which of these are justified depends on the real dataset.

TODO(dataset): implement after inspecting how inputs, change outputs and
network metadata appear in the official data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.graph.graph_builder import TransactionGraph


@dataclass(frozen=True)
class ClusterEvidence:
    heuristic: str            # e.g. "common_input"
    detail: dict[str, Any]    # e.g. {"txid": "...", "co_inputs": 3}


@dataclass
class EntityAssignment:
    wallet: str
    entity_id: str
    confidence: float | None          # None until a calibrated method exists
    evidence: list[ClusterEvidence] = field(default_factory=list)
    inferred: bool = True             # always True: clustering is an inference


class EntityClusterer(Protocol):
    name: str

    def cluster(self, graph: TransactionGraph) -> list[EntityAssignment]: ...


def cluster_entities(graph: TransactionGraph) -> list[EntityAssignment]:
    raise NotImplementedError("Entity clustering will be implemented once the dataset is mapped.")
