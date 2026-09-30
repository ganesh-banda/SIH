"""Chain the preprocessing steps: map -> normalize -> validate -> geo-enrich.

This is the only function most callers need. It does not write anything to
disk; persisting the outputs is the caller's (storage layer's) job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from app.ingestion.loader import IngestionResult
from app.ingestion.schema_mapping import CANONICAL_FIELDS, FieldKind, SchemaMapping, apply_mapping
from app.preprocessing.geo_features import enrich_ip_columns
from app.preprocessing.ip_geolocation import GeoIPService
from app.preprocessing.normalizer import normalize
from app.preprocessing.validator import ValidationReport, validate

logger = logging.getLogger(__name__)

IP_FIELDS = [name for name, spec in CANONICAL_FIELDS.items() if spec.kind is FieldKind.IP]


@dataclass
class PreprocessResult:
    frame: pl.DataFrame
    issues: pl.DataFrame
    report: ValidationReport


def preprocess(ingested: IngestionResult, mapping: SchemaMapping,
               geo: GeoIPService | None = None) -> PreprocessResult:
    canonical = apply_mapping(ingested.frame, mapping)
    normalized = normalize(canonical, mapping)
    validated = validate(normalized.frame, normalized.issues, mapping)
    frame = validated.frame
    if geo is not None:
        frame = enrich_ip_columns(frame, IP_FIELDS, geo)
        logger.info("Geo enrichment done: %s", geo.status())
    return PreprocessResult(frame=frame, issues=validated.issues, report=validated.report)
