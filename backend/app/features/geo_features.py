"""Behavioural geo/network features (IPs/countries/ASNs per wallet, changes, ...)

TODO(dataset): implement as a FeatureGroup once the official dataset is
mapped. Only features the real data genuinely supports will be added.
"""

from __future__ import annotations

import polars as pl

from app.features.base import FeatureContext


def compute(ctx: FeatureContext) -> pl.DataFrame:
    raise NotImplementedError("Pending dataset: geo_features")
