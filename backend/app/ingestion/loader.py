"""Format-agnostic dataset loader.

``load_dataset`` is the single entry point the rest of the pipeline uses. It:

1. detects the format from the file extension,
2. dispatches to the matching parser,
3. adds ``_record_index`` (0-based position in the source) for traceability,
4. records a SHA-256 of the source file so results can be tied to the exact
   input that produced them.

The source file is only ever opened for reading.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from app.ingestion.csv_parser import parse_csv
from app.ingestion.json_parser import JSON_LINES_SUFFIXES, parse_json
from app.ingestion.schema_mapping import RECORD_INDEX_COL
from app.ingestion.xml_parser import parse_xml

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".xml": "xml",
    **{suffix: "json" for suffix in JSON_LINES_SUFFIXES},
}


class UnsupportedFormatError(ValueError):
    pass


@dataclass
class IngestionResult:
    frame: pl.DataFrame
    source_path: Path
    file_format: str
    sha256: str

    @property
    def row_count(self) -> int:
        return self.frame.height

    def summary(self) -> dict:
        return {
            "source": self.source_path.name,
            "format": self.file_format,
            "sha256": self.sha256,
            "rows": self.row_count,
            "columns": [c for c in self.frame.columns if c != RECORD_INDEX_COL],
            "dtypes": {
                c: str(t) for c, t in self.frame.schema.items() if c != RECORD_INDEX_COL
            },
        }


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def detect_format(path: Path) -> str:
    try:
        return SUPPORTED_FORMATS[path.suffix.lower()]
    except KeyError:
        raise UnsupportedFormatError(
            f"Unsupported file type '{path.suffix}'. Supported: {sorted(SUPPORTED_FORMATS)}"
        ) from None


def load_dataset(path: Path, xml_record_tag: str | None = None) -> IngestionResult:
    """Load a CSV/TSV, JSON/JSONL or XML file into the raw internal frame."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    file_format = detect_format(path)
    logger.info("Ingesting %s as %s", path.name, file_format)

    if file_format == "csv":
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        frame = parse_csv(path, separator=sep)
    elif file_format == "json":
        frame = parse_json(path)
    else:
        frame = parse_xml(path, record_tag=xml_record_tag)

    if RECORD_INDEX_COL in frame.columns:
        raise ValueError(f"Dataset already contains reserved column '{RECORD_INDEX_COL}'")
    frame = frame.with_row_index(RECORD_INDEX_COL)

    return IngestionResult(frame=frame, source_path=path, file_format=file_format,
                           sha256=file_sha256(path))
