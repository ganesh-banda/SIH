"""Read-only graph queries and frontend serialisation.

``to_frontend_json`` returns ``{"nodes": [...], "edges": [...]}`` which maps
directly onto Cytoscape.js / vis-network / react-force-graph style inputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import networkx as nx

from app.graph.graph_builder import TransactionGraph
from app.graph.models import NodeType, node_id

DEFAULT_MAX_NODES = 300


class NodeNotFoundError(KeyError):
    pass


def _json_safe(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def ego_subgraph(graph: TransactionGraph, center: str, radius: int = 2,
                 max_nodes: int = DEFAULT_MAX_NODES) -> nx.MultiDiGraph:
    """Neighbourhood of ``center`` (ignoring edge direction), BFS-capped.

    The cap keeps API responses small for hub nodes; the response reports
    whether it was truncated.
    """
    if center not in graph.g:
        raise NodeNotFoundError(center)
    undirected = graph.g.to_undirected(as_view=True)
    keep: list[str] = [center]
    seen = {center}
    frontier = [center]
    truncated = False
    for _ in range(radius):
        nxt: list[str] = []
        for node in frontier:
            for nb in undirected.neighbors(node):
                if nb not in seen:
                    if len(keep) >= max_nodes:
                        truncated = True
                        break
                    seen.add(nb)
                    keep.append(nb)
                    nxt.append(nb)
        frontier = nxt
    sub = graph.g.subgraph(keep).copy()
    sub.graph["truncated"] = truncated
    sub.graph["center"] = center
    return sub


def wallet_subgraph(graph: TransactionGraph, address: str, radius: int = 2,
                    max_nodes: int = DEFAULT_MAX_NODES) -> nx.MultiDiGraph:
    return ego_subgraph(graph, node_id(NodeType.WALLET, address), radius, max_nodes)


def wallet_transactions(graph: TransactionGraph, address: str) -> dict[str, list[str]]:
    """TXIDs where the wallet is an input (``sent``) or output (``received``)."""
    wid = node_id(NodeType.WALLET, address)
    if wid not in graph.g:
        raise NodeNotFoundError(wid)
    sent = sorted({graph.g.nodes[v]["label"] for v in graph.g.successors(wid)})
    received = sorted({graph.g.nodes[u]["label"] for u in graph.g.predecessors(wid)})
    return {"sent": sent, "received": received}


def to_frontend_json(sub: nx.MultiDiGraph) -> dict[str, Any]:
    nodes = [
        {"id": n, **{k: _json_safe(v) for k, v in attrs.items()}}
        for n, attrs in sub.nodes(data=True)
    ]
    edges = [
        {"id": f"{u}|{v}|{k}", "source": u, "target": v,
         **{a: _json_safe(val) for a, val in attrs.items()}}
        for u, v, k, attrs in sub.edges(keys=True, data=True)
    ]
    return {"nodes": nodes, "edges": edges,
            "truncated": bool(sub.graph.get("truncated", False)),
            "center": sub.graph.get("center")}
