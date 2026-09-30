"""Dataset ingestion: CSV / JSON / XML -> one raw internal DataFrame."""

from app.ingestion.loader import IngestionResult, load_dataset
from app.ingestion.schema_mapping import CANONICAL_FIELDS, SchemaMapping, apply_mapping

__all__ = ["IngestionResult", "load_dataset", "CANONICAL_FIELDS", "SchemaMapping", "apply_mapping"]
