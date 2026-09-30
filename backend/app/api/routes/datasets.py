"""Dataset discovery and inspection (read-only), to support schema mapping.

Only files directly inside the configured raw directory can be read.
"""

from pathlib import Path

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_app_settings, get_store
from app.storage.duckdb_store import DuckDBStore
from app.api.schemas import CanonicalFieldInfo, DatasetFile, DatasetInspection, DatasetSummaryResponse
from app.config import Settings
from app.ingestion.loader import SUPPORTED_FORMATS, UnsupportedFormatError, load_dataset
from app.ingestion.schema_mapping import (
    CANONICAL_FIELDS, RECORD_INDEX_COL, SchemaMapping, SchemaMappingError,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])
summary_router = APIRouter(tags=["datasets"])


@summary_router.get("/dataset/summary", response_model=DatasetSummaryResponse)
def dataset_summary(store: DuckDBStore = Depends(get_store)):
    if not store.table_exists("transactions"):
        raise HTTPException(503, "Analysis has not been run")
    counts = store.query("""SELECT (SELECT count(*) FROM transactions) AS transactions,
        (SELECT count(*) FROM wallets) AS wallets,
        (SELECT count(*) FROM alerts) AS alerts""").to_dicts()[0]
    return counts


def _safe_raw_path(raw_dir: Path, name: str) -> Path:
    candidate = (raw_dir / name).resolve()
    if candidate.parent != raw_dir.resolve() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Dataset file not found in raw directory")
    return candidate


@router.get("", response_model=list[DatasetFile])
def list_datasets(settings: Settings = Depends(get_app_settings)) -> list[DatasetFile]:
    files = sorted(p for p in settings.raw_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    return [DatasetFile(name=p.name, size_bytes=p.stat().st_size,
                        format=SUPPORTED_FORMATS.get(p.suffix.lower())) for p in files]


@router.get("/canonical-fields", response_model=list[CanonicalFieldInfo])
def canonical_fields(settings: Settings = Depends(get_app_settings)) -> list[CanonicalFieldInfo]:
    mapped: dict[str, str] = {}
    try:
        mapped = SchemaMapping.from_file(settings.schema_mapping_path).mapped_fields
    except SchemaMappingError:
        pass
    return [CanonicalFieldInfo(name=f.name, kind=f.kind.value, description=f.description,
                               source=f.source, mapped_to=mapped.get(f.name))
            for f in CANONICAL_FIELDS.values()]


@router.get("/{name}/inspect", response_model=DatasetInspection)
def inspect_dataset(name: str, sample_rows: int = Query(5, ge=0, le=20),
                    settings: Settings = Depends(get_app_settings)) -> DatasetInspection:
    path = _safe_raw_path(settings.raw_dir, name)
    try:
        result = load_dataset(path)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except (ValueError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse dataset: {exc}") from exc

    frame = result.frame.drop(RECORD_INDEX_COL)
    summary = result.summary()
    return DatasetInspection(
        **summary,
        null_counts={c: int(v) for c, v in frame.null_count().row(0, named=True).items()}
        if frame.width else {},
        sample=frame.head(sample_rows).to_dicts(),
    )
