"""Graph node/edge vocabulary.

Node ids are prefixed by type (``wallet:...``, ``tx:...``, ``ip:...``,
``entity:...``) so a wallet address can never collide with a TXID or IP.
"""

from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    WALLET = "wallet"
    TRANSACTION = "tx"
    IP = "ip"
    ENTITY = "entity"


class EdgeType(str, Enum):
    INPUT = "input"          # wallet -> transaction (wallet funds the tx)
    OUTPUT = "output"        # transaction -> wallet (tx pays the wallet)
    OBSERVED_SRC = "observed_src"  # ip -> transaction (tx seen coming from this IP)
    OBSERVED_DST = "observed_dst"  # ip -> transaction (tx seen going to this IP)
    MEMBER_OF = "member_of"  # wallet -> entity (INFERRED, never proof of ownership)


def node_id(node_type: NodeType, value: str) -> str:
    return f"{node_type.value}:{value}"


def split_node_id(nid: str) -> tuple[NodeType, str]:
    prefix, _, value = nid.partition(":")
    return NodeType(prefix), value
