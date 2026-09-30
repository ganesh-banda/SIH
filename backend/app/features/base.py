"""Feature-group interface.

A feature group computes one table keyed by an id column (e.g. a wallet or
transaction id). The pipeline joins groups on that key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import polars as pl


@dataclass
class FeatureContext:
    """Everything a feature group may need. Filled by the pipeline."""

    records: pl.DataFrame
    graph: Any | None = None  # TransactionGraph, typed loosely to avoid import cycles
    extras: dict[str, Any] = field(default_factory=dict)


class FeatureGroup(Protocol):
    name: str
    key: str  # id column the output is keyed on

    def compute(self, ctx: FeatureContext) -> pl.DataFrame: ...
