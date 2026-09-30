"""Canonical internal schema and the dataset -> canonical column mapping.

The *canonical* field names below are taken from the "minimum fields" list in
the SIH problem statement (PS-5, NTRO). They are the names the rest of the
pipeline uses internally. They are NOT assumed to be the column names of the
official dataset.

Once the dataset is inspected, ``config/schema_mapping.json`` is filled in to
say which raw column feeds each canonical field. Columns that are not mapped
are carried through untouched (e.g. labels, extra network metadata), so no
information is lost while we decide what to do with them.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)


class FieldKind(str, Enum):
    """How a canonical field should be normalized."""

    TIMESTAMP = "timestamp"
    IP = "ip"
    PORT = "port"
    TXID = "txid"
    ADDRESS_LIST = "address_list"
    AMOUNT_LIST = "amount_list"
    NUMBER = "number"
    CATEGORY = "category"


@dataclass(frozen=True)
class CanonicalField:
    name: str
    kind: FieldKind
    description: str
    source: str  # where we got this field from, for traceability


_PS = "PS-5 minimum fields"
_PS_OBJ = "PS-5 challenge objectives"

CANONICAL_FIELDS: dict[str, CanonicalField] = {
    f.name: f
    for f in (
        CanonicalField("timestamp", FieldKind.TIMESTAMP, "Observation / transaction time", _PS),
        CanonicalField("src_ip", FieldKind.IP, "Source IP of the network observation", _PS),
        CanonicalField("dst_ip", FieldKind.IP, "Destination IP of the network observation", _PS),
        CanonicalField("src_port", FieldKind.PORT, "Source port", _PS),
        CanonicalField("dst_port", FieldKind.PORT, "Destination port", _PS),
        CanonicalField("txid", FieldKind.TXID, "Transaction identifier", _PS),
        CanonicalField("input_addresses", FieldKind.ADDRESS_LIST, "Input wallet addresses", _PS),
        CanonicalField("output_addresses", FieldKind.ADDRESS_LIST, "Output wallet addresses", _PS),
        CanonicalField("input_amounts", FieldKind.AMOUNT_LIST, "Amounts per input (unit TBD)", _PS),
        CanonicalField("output_amounts", FieldKind.AMOUNT_LIST, "Amounts per output (unit TBD)", _PS),
        CanonicalField("fee", FieldKind.NUMBER, "Transaction fee (unit TBD)", _PS_OBJ),
        CanonicalField("script_type", FieldKind.CATEGORY, "Script type", _PS_OBJ),
        # Geo fields the dataset MAY supply itself. Kept separate from the
        # GeoLite-derived columns so the two can be cross-checked.
        CanonicalField("dataset_geo_country", FieldKind.CATEGORY, "Country as supplied by dataset", _PS),
        CanonicalField("dataset_asn", FieldKind.CATEGORY, "ASN as supplied by dataset", _PS),
    )
}

# Column added by the loader so every row can be traced back to its source.
RECORD_INDEX_COL = "_record_index"


class SchemaMappingError(ValueError):
    """Raised when the schema mapping is missing, empty or inconsistent."""


@dataclass
class SchemaMapping:
    """Mapping from raw dataset columns to canonical fields.

    Attributes:
        fields: canonical name -> raw column name (``None`` = not present).
        required_fields: canonical fields whose absence makes a record invalid.
        list_delimiter: delimiter for list fields stored as plain strings in
            CSV (``None`` = expect JSON arrays such as ``["a","b"]``).
        timestamp_unit: ``"s"``/``"ms"``/``"us"`` for epoch timestamps, or
            ``None`` to auto-detect (ISO strings or epoch by magnitude).
        naive_timestamps_are_utc: interpret timezone-less timestamps as UTC.
        xml_record_tag: XML element name for one record (``None`` = auto).
    """

    fields: dict[str, str | None] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    list_delimiter: str | None = None
    timestamp_unit: str | None = None
    naive_timestamps_are_utc: bool = True
    xml_record_tag: str | None = None

    @property
    def mapped_fields(self) -> dict[str, str]:
        return {k: v for k, v in self.fields.items() if v}

    def validate(self) -> None:
        unknown = set(self.fields) - set(CANONICAL_FIELDS)
        if unknown:
            raise SchemaMappingError(f"Unknown canonical fields in mapping: {sorted(unknown)}")
        missing_required = [f for f in self.required_fields if f not in self.mapped_fields]
        if missing_required:
            raise SchemaMappingError(f"Required fields are not mapped: {missing_required}")
        raw_cols = list(self.mapped_fields.values())
        if len(raw_cols) != len(set(raw_cols)):
            raise SchemaMappingError("The same raw column is mapped to two canonical fields")
        if self.timestamp_unit not in (None, "s", "ms", "us"):
            raise SchemaMappingError("timestamp_unit must be null, 's', 'ms' or 'us'")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchemaMapping":
        mapping = cls(
            fields=dict(data.get("fields", {})),
            required_fields=list(data.get("required_fields", [])),
            list_delimiter=data.get("list_delimiter"),
            timestamp_unit=data.get("timestamp_unit"),
            naive_timestamps_are_utc=bool(data.get("naive_timestamps_are_utc", True)),
            xml_record_tag=data.get("xml_record_tag"),
        )
        mapping.validate()
        return mapping

    @classmethod
    def from_file(cls, path: Path) -> "SchemaMapping":
        if not path.exists():
            raise SchemaMappingError(
                f"Schema mapping not found at {path}. Copy "
                "config/schema_mapping.example.json and fill it in after inspecting the dataset."
            )
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def apply_mapping(frame: pl.DataFrame, mapping: SchemaMapping) -> pl.DataFrame:
    """Rename raw columns to canonical names.

    Unmapped raw columns are kept unchanged. A raw column that would collide
    with a canonical name it is *not* mapped to is prefixed with ``raw_``.
    """
    mapped = mapping.mapped_fields
    if not mapped:
        raise SchemaMappingError("Schema mapping has no fields mapped yet (dataset not mapped).")

    absent = [raw for raw in mapped.values() if raw not in frame.columns]
    if absent:
        raise SchemaMappingError(f"Mapped raw columns not found in dataset: {absent}")

    rename = {raw: canonical for canonical, raw in mapped.items()}
    targets = set(rename.values())
    for col in frame.columns:
        if col not in rename and col in targets:
            rename[col] = f"raw_{col}"
    logger.info("Applying schema mapping: %d canonical fields mapped", len(mapped))
    return frame.rename(rename)
