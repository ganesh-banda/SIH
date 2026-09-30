"""JSON parser.

Supports the three layouts datasets usually come in:

* a top-level array of records: ``[{...}, {...}]``
* a top-level object wrapping the array: ``{"records": [...]}``
  (any single key whose value is a list of objects)
* JSON Lines / NDJSON: one object per line (``.jsonl`` / ``.ndjson``)

Nested objects are flattened with dotted keys (``network.src_ip``).
Lists are preserved as lists, because the PS describes list-valued fields
such as input/output addresses.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Iterator

import polars as pl

logger = logging.getLogger(__name__)

JSON_LINES_SUFFIXES = {".jsonl", ".ndjson"}


class JSONLayoutError(ValueError):
    """Raised when the JSON document is not a recognisable list of records."""


def flatten_record(record: dict[str, Any], parent: str = "", sep: str = ".") -> dict[str, Any]:
    """Flatten nested dicts; leave lists and scalars untouched."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{parent}{sep}{key}" if parent else str(key)
        if isinstance(value, dict):
            flat.update(flatten_record(value, name, sep))
        else:
            flat[name] = value
    return flat


def _extract_records(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        records = document
    elif isinstance(document, dict):
        list_keys = [k for k, v in document.items() if isinstance(v, list)]
        if len(list_keys) != 1:
            raise JSONLayoutError(
                "Top-level JSON object must contain exactly one list of records; "
                f"found list keys: {list_keys}"
            )
        records = document[list_keys[0]]
    else:
        raise JSONLayoutError("JSON root must be an array or an object")

    if not all(isinstance(r, dict) for r in records):
        raise JSONLayoutError("Every record must be a JSON object")
    return records


def _iter_json_lines(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JSONLayoutError(f"Invalid JSON on line {line_no}: {exc.msg}") from exc
            if not isinstance(obj, dict):
                raise JSONLayoutError(f"Line {line_no} is not a JSON object")
            yield obj


def records_to_frame(records: Iterable[dict[str, Any]]) -> pl.DataFrame:
    """Build a DataFrame from (possibly heterogeneous) records.

    ``infer_schema_length=None`` scans all rows so a field that only appears
    late in the file is not lost.
    """
    flat = [flatten_record(r) for r in records]
    if not flat:
        return pl.DataFrame()
    return pl.from_dicts(flat, infer_schema_length=None, strict=False)


def parse_json(path: Path) -> pl.DataFrame:
    """Parse a JSON or JSON Lines file into a DataFrame."""
    if path.suffix.lower() in JSON_LINES_SUFFIXES:
        records: Iterable[dict[str, Any]] = _iter_json_lines(path)
    else:
        with path.open("r", encoding="utf-8") as handle:
            records = _extract_records(json.load(handle))
    frame = records_to_frame(records)
    logger.info("JSON parsed: %s (%d rows, %d columns)", path.name, frame.height, frame.width)
    return frame
