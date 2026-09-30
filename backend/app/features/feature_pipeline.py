"""Run registered feature groups and join their outputs.

Implemented now: the orchestration and the identifier-leakage guard.
TODO(dataset): register real feature groups once columns are known.
"""

from __future__ import annotations

import logging

import polars as pl

from app.features.base import FeatureContext, FeatureGroup

logger = logging.getLogger(__name__)

# Canonical columns that are identifiers and must never become model inputs.
IDENTIFIER_COLUMNS = frozenset({
    "txid", "input_addresses", "output_addresses", "src_ip", "dst_ip",
    "_record_index", "wallet_id", "entity_id",
})


class IdentifierLeakError(ValueError):
    pass


def assert_no_identifier_columns(features: pl.DataFrame, key: str) -> None:
    """Fail if an identifier (other than the join key) is in a feature table.

    The key is kept only to map predictions back to real wallets/entities and
    must be dropped before training.
    """
    leaked = sorted((set(features.columns) - {key}) & IDENTIFIER_COLUMNS)
    if leaked:
        raise IdentifierLeakError(f"Identifier columns in feature table: {leaked}")


def run_feature_groups(groups: list[FeatureGroup], ctx: FeatureContext) -> pl.DataFrame:
    if not groups:
        raise ValueError("No feature groups registered (dataset not mapped yet).")
    keys = {g.key for g in groups}
    if len(keys) != 1:
        raise ValueError(f"All groups in one run must share a key; got {sorted(keys)}")
    key = keys.pop()

    result: pl.DataFrame | None = None
    for group in groups:
        table = group.compute(ctx)
        assert_no_identifier_columns(table, key)
        prefixed = table.rename({c: f"{group.name}__{c}" for c in table.columns if c != key})
        result = prefixed if result is None else result.join(prefixed, on=key, how="full",
                                                             coalesce=True)
        logger.info("Feature group '%s' computed: %d rows", group.name, table.height)
    assert result is not None
    return result
