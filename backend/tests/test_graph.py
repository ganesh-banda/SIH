from datetime import datetime, timezone

import polars as pl
import pytest

from app.graph.graph_builder import build_graph
from app.graph.graph_queries import (
    NodeNotFoundError, ego_subgraph, to_frontend_json, wallet_subgraph, wallet_transactions,
)
from app.graph.models import NodeType, node_id, split_node_id

T = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _frame(rows):
    base = {"_record_index": None, "txid": None, "timestamp": T, "fee": None,
            "input_addresses": None, "output_addresses": None,
            "input_amounts": None, "output_amounts": None,
            "src_ip": None, "dst_ip": None, "src_port": None, "dst_port": None,
            "src_ip_category": None, "dst_ip_category": None,
            "_is_valid": True, "_is_duplicate": False}
    return pl.DataFrame([base | r for r in rows], infer_schema_length=None)


@pytest.fixture
def graph():
    return build_graph(_frame([
        {"_record_index": 0, "txid": "t1", "input_addresses": ["A"], "output_addresses": ["B", "C"],
         "input_amounts": [3.0], "output_amounts": [2.0, 0.9], "src_ip": "8.8.8.8",
         "dst_ip": "1.1.1.1", "src_port": 8333},
        # same tx observed again between other peers
        {"_record_index": 1, "txid": "t1", "input_addresses": ["A"], "output_addresses": ["B", "C"],
         "input_amounts": [3.0], "output_amounts": [2.0, 0.9], "src_ip": "1.1.1.1",
         "dst_ip": "9.9.9.9"},
        {"_record_index": 2, "txid": "t2", "input_addresses": ["B"], "output_addresses": ["D"],
         "input_amounts": [2.0], "output_amounts": [1.9]},
        {"_record_index": 3, "txid": "t3", "input_addresses": ["X"], "_is_valid": False},
        {"_record_index": 4, "txid": "t2", "input_addresses": ["B"], "_is_duplicate": True},
    ]))


def test_node_ids_do_not_collide():
    assert node_id(NodeType.WALLET, "abc") != node_id(NodeType.TRANSACTION, "abc")
    assert split_node_id("wallet:abc") == (NodeType.WALLET, "abc")


def test_counts_and_filtering(graph):
    s = graph.summary()
    assert s["tx"] == 2           # t3 is invalid -> skipped
    assert s["wallet"] == 4       # A B C D (X skipped)
    assert s["ip"] == 3


def test_repeated_observations_do_not_duplicate_io_edges(graph):
    g = graph.g
    assert g.number_of_edges("wallet:A", "tx:t1") == 1
    assert g.number_of_edges("tx:t1", "wallet:B") == 1
    # but each observation is kept
    assert g.number_of_edges("ip:1.1.1.1", "tx:t1") == 2  # dst in rec 0, src in rec 1


def test_edge_amounts(graph):
    edge = graph.g.get_edge_data("tx:t1", "wallet:C")["out:1"]
    assert edge["amount"] == 0.9 and edge["edge_type"] == "output"


def test_wallet_transactions(graph):
    assert wallet_transactions(graph, "B") == {"sent": ["t2"], "received": ["t1"]}
    with pytest.raises(NodeNotFoundError):
        wallet_transactions(graph, "nope")


def test_subgraph_and_frontend_json(graph):
    sub = wallet_subgraph(graph, "A", radius=2)
    assert {"wallet:A", "tx:t1", "wallet:B", "wallet:C"} <= set(sub.nodes)
    payload = to_frontend_json(sub)
    assert payload["center"] == "wallet:A" and payload["truncated"] is False
    assert all({"id", "source", "target", "edge_type"} <= set(e) for e in payload["edges"])
    tx = next(n for n in payload["nodes"] if n["id"] == "tx:t1")
    assert tx["first_seen"] == T.isoformat()  # datetimes are JSON-safe


def test_subgraph_cap(graph):
    sub = ego_subgraph(graph, "tx:t1", radius=3, max_nodes=3)
    assert sub.number_of_nodes() == 3
    assert to_frontend_json(sub)["truncated"] is True


def test_requires_txid():
    with pytest.raises(ValueError):
        build_graph(pl.DataFrame({"a": [1]}))
