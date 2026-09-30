"""Attach GeoLite2 context to records and cross-check dataset-supplied geo.

What is implemented (dataset-independent):

* ``enrich_ip_columns`` - join GeoLite results onto any IP columns,
  prefixed per column (``src_ip`` -> ``src_ip_geo_country`` ...).
* ``cross_check_country`` / ``cross_check_asn`` - compare a geo value the
  dataset supplies with what GeoLite says. Result is ``match`` / ``mismatch``
  / ``unknown``; it is a data-quality signal, NOT a risk signal.
* ``haversine_km`` - great-circle distance helper.

REMINDER: crossing a border (e.g. India -> Germany) is normal Bitcoin P2P
behaviour and must never raise risk on its own.

TODO(dataset): behavioural geo features (country_change, asn_change,
unique countries/ASNs per wallet, rapid geographical change, ...). These
depend on how IPs relate to wallets in the real data (is src_ip the
broadcasting node? a relay peer?), which we cannot know yet.
"""

from __future__ import annotations

import math

import polars as pl

from app.preprocessing.ip_geolocation import GeoIPService

EARTH_RADIUS_KM = 6371.0088

GEO_COLUMNS_TO_ATTACH = (
    "ip_category", "lookup_status", "country", "country_iso", "region", "city",
    "latitude", "longitude", "accuracy_radius_km", "timezone", "asn", "asn_org",
    "data_source",
)


def enrich_ip_columns(
    frame: pl.DataFrame, ip_columns: list[str], service: GeoIPService
) -> pl.DataFrame:
    """Left-join GeoLite results for each IP column. Row count is unchanged."""
    present = [c for c in ip_columns if c in frame.columns]
    if not present:
        return frame

    all_ips = pl.concat([frame.get_column(c).cast(pl.Utf8) for c in present]).drop_nulls()
    lookup = service.lookup_many(all_ips.to_list())

    for column in present:
        renamed = lookup.select(
            pl.col("ip").alias(column),
            *[pl.col(g).alias(f"{column}_geo_{g}") for g in GEO_COLUMNS_TO_ATTACH],
        )
        frame = frame.join(renamed, on=column, how="left", nulls_equal=False)
    return frame


def _cross_check(dataset_col: pl.Expr, geolite_col: pl.Expr) -> pl.Expr:
    left = dataset_col.cast(pl.Utf8).str.strip_chars().str.to_uppercase()
    right = geolite_col.cast(pl.Utf8).str.strip_chars().str.to_uppercase()
    return (
        pl.when(left.is_null() | right.is_null() | (left == "") | (right == ""))
        .then(pl.lit("unknown"))
        .when(left == right)
        .then(pl.lit("match"))
        .otherwise(pl.lit("mismatch"))
    )


def cross_check_country(frame: pl.DataFrame, dataset_col: str, geolite_iso_col: str,
                        out_col: str) -> pl.DataFrame:
    """Compare a dataset country value with the GeoLite ISO code.

    TODO(dataset): if the dataset stores country *names* rather than ISO
    codes, map names to ISO codes before calling this.
    """
    return frame.with_columns(_cross_check(pl.col(dataset_col), pl.col(geolite_iso_col)).alias(out_col))


def cross_check_asn(frame: pl.DataFrame, dataset_col: str, geolite_asn_col: str,
                    out_col: str) -> pl.DataFrame:
    """Compare dataset ASN with GeoLite ASN, tolerating an 'AS' prefix."""
    dataset_asn = pl.col(dataset_col).cast(pl.Utf8).str.strip_chars().str.replace(r"(?i)^AS", "")
    return frame.with_columns(_cross_check(dataset_asn, pl.col(geolite_asn_col)).alias(out_col))


def haversine_km(lat1: float | None, lon1: float | None,
                 lat2: float | None, lon2: float | None) -> float | None:
    """Great-circle distance in km, or None if any coordinate is missing."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
