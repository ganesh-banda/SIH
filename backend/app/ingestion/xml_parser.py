"""XML parser (streaming).

Uses ``xml.etree.ElementTree.iterparse`` so large files are not loaded into
memory as a full tree. Assumed layout: a root element containing repeated
record elements. For each record element:

* attributes become fields,
* child elements with text become fields,
* a child tag that repeats (e.g. several ``<address>`` under ``<inputs>``)
  becomes a list,
* nested children are flattened with dotted names (``inputs.address``).

The record tag is configured in the schema mapping (``xml_record_tag``). If it
is not set, the tag of the root's first child is used.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import polars as pl

from app.ingestion.json_parser import records_to_frame

logger = logging.getLogger(__name__)


def _local(tag: str) -> str:
    """Strip an XML namespace: '{ns}name' -> 'name'."""
    return tag.rsplit("}", 1)[-1]


def _add(record: dict[str, Any], key: str, value: Any) -> None:
    if key in record:
        existing = record[key]
        record[key] = existing + [value] if isinstance(existing, list) else [existing, value]
    else:
        record[key] = value


def element_to_record(element: ET.Element, prefix: str = "") -> dict[str, Any]:
    """Convert one record element into a flat dict."""
    record: dict[str, Any] = {}
    for attr, value in element.attrib.items():
        _add(record, f"{prefix}{_local(attr)}", value)
    for child in element:
        name = f"{prefix}{_local(child.tag)}"
        if len(child) or child.attrib:
            for k, v in element_to_record(child, prefix=f"{name}.").items():
                _add(record, k, v)
        else:
            text = child.text.strip() if child.text and child.text.strip() else None
            _add(record, name, text)
    return record


def _detect_record_tag(path: Path) -> str:
    depth = 0
    for event, elem in ET.iterparse(path, events=("start",)):
        depth += 1
        if depth == 2:
            return _local(elem.tag)
    raise ValueError("XML file has no record elements under the root")


def _harmonise_lists(records: list[dict[str, Any]]) -> None:
    """If a key is a list in any record, make it a list in every record.

    A repeated tag that happens to occur once in some record would otherwise
    produce a scalar there and a list elsewhere.
    """
    list_keys = {k for r in records for k, v in r.items() if isinstance(v, list)}
    for record in records:
        for key in list_keys:
            value = record.get(key)
            if value is not None and not isinstance(value, list):
                record[key] = [value]


def parse_xml(path: Path, record_tag: str | None = None) -> pl.DataFrame:
    """Stream-parse an XML file into a DataFrame."""
    tag = record_tag or _detect_record_tag(path)
    records: list[dict[str, Any]] = []
    for _event, elem in ET.iterparse(path, events=("end",)):
        if _local(elem.tag) == tag:
            records.append(element_to_record(elem))
            elem.clear()  # free memory as we go
    _harmonise_lists(records)
    frame = records_to_frame(records)
    logger.info(
        "XML parsed: %s (record tag '%s', %d rows, %d columns)",
        path.name, tag, frame.height, frame.width,
    )
    return frame
