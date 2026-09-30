"""Build the wallet / transaction / IP graph from normalized records.

Uses a NetworkX ``MultiDiGraph``. All graph access elsewhere goes through
``TransactionGraph`` and ``graph_queries`` so the backend can be swapped for
igraph later without touching callers.

Only canonical fields are used, and only if present in the frame. Edges carry
small attributes (amount, timestamp, fee, ports, record index), never whole
raw records; the record index points back to full details in storage.

Edge keys are deterministic, so re-adding the same record is idempotent:
  input/output edges:  "in:<position>" / "out:<position>"   (one per tx slot)
  IP observation edges: "obs:<record_index>"               (one per record)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import networkx as nx
import polars as pl

from app.graph.models import EdgeType, NodeType, node_id

logger = logging.getLogger(__name__)


class TransactionGraph:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    # --- nodes -----------------------------------------------------------
    def _add_node(self, ntype: NodeType, value: str, **attrs: Any) -> str:
        nid = node_id(ntype, value)
        if nid in self.g:
            # fill in attributes we did not know before, never overwrite
            for key, val in attrs.items():
                if val is not None and self.g.nodes[nid].get(key) is None:
                    self.g.nodes[nid][key] = val
        else:
            self.g.add_node(nid, node_type=ntype.value, label=value, **attrs)
        return nid

    def add_wallet(self, address: str) -> str:
        return self._add_node(NodeType.WALLET, address)

    def add_transaction(self, txid: str, timestamp: datetime | None = None,
                        fee: float | None = None) -> str:
        return self._add_node(NodeType.TRANSACTION, txid, first_seen=timestamp, fee=fee)

    def add_ip(self, ip: str, category: str | None = None) -> str:
        return self._add_node(NodeType.IP, ip, ip_category=category)

    # --- edges -----------------------------------------------------------
    def add_input(self, address: str, txid: str, position: int,
                  amount: float | None = None) -> None:
        self.g.add_edge(self.add_wallet(address), node_id(NodeType.TRANSACTION, txid),
                        key=f"in:{position}", edge_type=EdgeType.INPUT.value, amount=amount)

    def add_output(self, txid: str, address: str, position: int,
                   amount: float | None = None) -> None:
        self.g.add_edge(node_id(NodeType.TRANSACTION, txid), self.add_wallet(address),
                        key=f"out:{position}", edge_type=EdgeType.OUTPUT.value, amount=amount)

    def add_observation(self, ip: str, txid: str, role: EdgeType, record_index: int,
                        timestamp: datetime | None = None, port: int | None = None,
                        category: str | None = None) -> None:
        self.g.add_edge(self.add_ip(ip, category), node_id(NodeType.TRANSACTION, txid),
                        key=f"obs:{role.value}:{record_index}", edge_type=role.value,
                        timestamp=timestamp, port=port, record_index=record_index)

    # --- summary ---------------------------------------------------------
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {t.value: 0 for t in NodeType}
        for _, ntype in self.g.nodes(data="node_type"):
            counts[ntype] = counts.get(ntype, 0) + 1
        return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges(), **counts}


def _get(row: dict, key: str) -> Any:
    return row.get(key)


def _amount_at(amounts: list | None, addresses: list, i: int) -> float | None:
    if amounts is None or len(amounts) != len(addresses):
        return None  # mismatched lists were already flagged by the validator
    return amounts[i]


def build_graph(frame: pl.DataFrame, only_valid: bool = True,
                skip_duplicates: bool = True) -> TransactionGraph:
    """Build a TransactionGraph from a preprocessed canonical frame."""
    if "txid" not in frame.columns:
        raise ValueError("Cannot build graph: canonical field 'txid' is not mapped")

    work = frame.filter(pl.col("txid").is_not_null())
    if only_valid and "_is_valid" in work.columns:
        work = work.filter(pl.col("_is_valid"))
    if skip_duplicates and "_is_duplicate" in work.columns:
        work = work.filter(~pl.col("_is_duplicate"))

    graph = TransactionGraph()
    io_done: set[str] = set()  # a tx's inputs/outputs are added once, however often it is observed

    for row in work.iter_rows(named=True):
        txid = row["txid"]
        graph.add_transaction(txid, _get(row, "timestamp"), _get(row, "fee"))

        if txid not in io_done:
            ins = _get(row, "input_addresses") or []
            for i, addr in enumerate(ins):
                graph.add_input(addr, txid, i, _amount_at(_get(row, "input_amounts"), ins, i))
            outs = _get(row, "output_addresses") or []
            for i, addr in enumerate(outs):
                graph.add_output(txid, addr, i, _amount_at(_get(row, "output_amounts"), outs, i))
            if ins or outs:
                io_done.add(txid)

        for ip_col, port_col, role in (("src_ip", "src_port", EdgeType.OBSERVED_SRC),
                                       ("dst_ip", "dst_port", EdgeType.OBSERVED_DST)):
            ip = _get(row, ip_col)
            if ip:
                graph.add_observation(ip, txid, role, row["_record_index"],
                                      _get(row, "timestamp"), _get(row, port_col),
                                      _get(row, f"{ip_col}_category"))

    logger.info("Graph built: %s", graph.summary())
    return graph
