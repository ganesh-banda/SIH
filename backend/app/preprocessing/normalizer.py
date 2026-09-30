"""Normalize canonical fields into consistent types.

Input: a frame that has already been passed through ``apply_mapping`` (so it
uses canonical column names). Only canonical fields that are present are
touched; everything else passes through unchanged.

Per field kind:
    timestamp     -> UTC Datetime (ISO strings or epoch s/ms/us)
    ip            -> canonical text + ``<col>_category`` column
    port          -> Int32 in 0..65535
    txid          -> stripped; lower-cased if it is hex
    address_list  -> list[str], whitespace-stripped; bech32 lower-cased
    amount_list   -> list[f64]
    number        -> f64
    category      -> stripped string, empty -> null

A value that cannot be converted becomes null AND produces an issue row, so
the change is always visible. The original file on disk is never modified;
``_record_index`` links each row back to it.

Amounts are kept in whatever unit the dataset uses.
TODO(dataset): confirm BTC vs satoshi; if satoshi, switch amounts to Int64.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import polars as pl

from app.ingestion.schema_mapping import (
    CANONICAL_FIELDS, RECORD_INDEX_COL, FieldKind, SchemaMapping,
)
from app.preprocessing.ip_validation import IPCategory, classify_ip
from app.preprocessing.issues import IssueCode, IssueCollector

logger = logging.getLogger(__name__)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_BECH32_PREFIXES = ("bc1", "tb1", "bcrt1")
_DETAIL_MAX = 80


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= _DETAIL_MAX else text[: _DETAIL_MAX - 3] + "..."


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


# --- scalar converters --------------------------------------------------
# Each returns the converted value, or raises ValueError.

def parse_timestamp(value: Any, unit: str | None = None,
                    naive_is_utc: bool = True) -> datetime:
    """Parse ISO-8601 strings or epoch numbers into an aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            number = float(text)
        except ValueError:
            number = None
        if number is not None:
            if not math.isfinite(number):
                raise ValueError("non-finite epoch")
            chosen = unit or ("s" if abs(number) < 1e11 else "ms" if abs(number) < 1e14 else "us")
            divisor = {"s": 1, "ms": 1_000, "us": 1_000_000}[chosen]
            return datetime.fromtimestamp(number / divisor, tz=timezone.utc)
        dt = datetime.fromisoformat(text)  # py3.11+: accepts 'Z' and ' ' separator
    if dt.tzinfo is None:
        if not naive_is_utc:
            raise ValueError("timestamp has no timezone")
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    number = float(str(value).strip()) if isinstance(value, str) else float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite number")
    return number


def parse_port(value: Any) -> int:
    number = parse_number(value)
    if not number.is_integer() or not 0 <= number <= 65535:
        raise ValueError("port out of range")
    return int(number)


def parse_list(value: Any, delimiter: str | None = None) -> list[Any]:
    """Accept a real list, a JSON/Python list literal, or a delimited string.

    A plain string with no configured delimiter is treated as a one-item list.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, pl.Series):
        return value.to_list()
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = ast.literal_eval(text)  # e.g. "['a', 'b']" from pandas exports
        if not isinstance(parsed, list):
            raise ValueError("not a list")
        return parsed
    if delimiter:
        return [part.strip() for part in text.split(delimiter)]
    return [text]


def normalize_address(address: Any) -> str:
    """Strip whitespace; lower-case bech32 (case-insensitive by spec).

    Base58 addresses are case-sensitive and left as-is. No checksum
    validation: synthetic datasets may use non-checksummed addresses.
    """
    text = str(address).strip()
    if not text:
        raise ValueError("empty address")
    if text.lower().startswith(_BECH32_PREFIXES):
        return text.lower()
    return text


def normalize_txid(value: Any) -> tuple[str, bool]:
    """Return (normalized txid, looks_like_real_bitcoin_txid)."""
    text = str(value).strip()
    lowered = text.lower()
    if _HEX64.match(lowered):
        return lowered, True
    return text, False


# --- column-level normalization -----------------------------------------

@dataclass
class NormalizationResult:
    frame: pl.DataFrame
    issues: IssueCollector


def _convert_column(
    values: list[Any], indices: list[int], field_name: str, code: IssueCode,
    convert: Callable[[Any], Any], issues: IssueCollector,
) -> list[Any]:
    out: list[Any] = []
    for idx, value in zip(indices, values):
        if _is_blank(value):
            issues.add(idx, field_name, IssueCode.MISSING_VALUE)
            out.append(None)
            continue
        try:
            out.append(convert(value))
        except (ValueError, TypeError, SyntaxError, OverflowError):
            issues.add(idx, field_name, code, f"value={_short(value)}")
            out.append(None)
    return out


def _normalize_ip_column(values: list[Any], indices: list[int], name: str,
                         issues: IssueCollector) -> tuple[list, list]:
    normalized, categories = [], []
    for idx, value in zip(indices, values):
        if _is_blank(value):
            issues.add(idx, name, IssueCode.MISSING_VALUE)
            normalized.append(None)
            categories.append(None)
            continue
        info = classify_ip(str(value))
        normalized.append(info.normalized)
        categories.append(info.category.value)
        if info.category is IPCategory.INVALID:
            issues.add(idx, name, IssueCode.INVALID_IP, f"value={_short(value)}")
        elif not info.is_public:
            issues.add(idx, name, IssueCode.NON_PUBLIC_IP, info.category.value)
    return normalized, categories


def _normalize_amount_list(raw: Any, delimiter: str | None, idx: int, name: str,
                           issues: IssueCollector) -> list[float] | None:
    items = parse_list(raw, delimiter)
    amounts: list[float] = []
    for item in items:
        amount = parse_number(item)  # ValueError bubbles up -> INVALID_NUMBER
        amounts.append(amount)
    if any(a < 0 for a in amounts):
        issues.add(idx, name, IssueCode.NEGATIVE_AMOUNT)
    return amounts


def normalize(frame: pl.DataFrame, mapping: SchemaMapping) -> NormalizationResult:
    """Normalize every canonical field present in ``frame``."""
    issues = IssueCollector()
    indices = frame.get_column(RECORD_INDEX_COL).to_list()
    new_columns: list[pl.Series] = []
    delim = mapping.list_delimiter

    for name, spec in CANONICAL_FIELDS.items():
        if name not in frame.columns:
            continue
        values = frame.get_column(name).to_list()
        kind = spec.kind

        if kind is FieldKind.TIMESTAMP:
            conv = _convert_column(
                values, indices, name, IssueCode.INVALID_TIMESTAMP,
                lambda v: parse_timestamp(v, mapping.timestamp_unit,
                                          mapping.naive_timestamps_are_utc),
                issues)
            new_columns.append(pl.Series(name, conv, dtype=pl.Datetime("us", "UTC")))

        elif kind is FieldKind.IP:
            norm, cats = _normalize_ip_column(values, indices, name, issues)
            new_columns += [pl.Series(name, norm, dtype=pl.Utf8),
                            pl.Series(f"{name}_category", cats, dtype=pl.Utf8)]

        elif kind is FieldKind.PORT:
            conv = _convert_column(values, indices, name, IssueCode.INVALID_PORT,
                                   parse_port, issues)
            new_columns.append(pl.Series(name, conv, dtype=pl.Int32))

        elif kind is FieldKind.TXID:
            conv = []
            for idx, value in zip(indices, values):
                if _is_blank(value):
                    issues.add(idx, name, IssueCode.MISSING_VALUE)
                    conv.append(None)
                    continue
                txid, looks_real = normalize_txid(value)
                if not looks_real:
                    issues.add(idx, name, IssueCode.INVALID_TXID_FORMAT,
                               "not 64 hex characters")
                conv.append(txid)
            new_columns.append(pl.Series(name, conv, dtype=pl.Utf8))

        elif kind is FieldKind.ADDRESS_LIST:
            conv = _convert_column(
                values, indices, name, IssueCode.INVALID_LIST,
                lambda v: [normalize_address(a) for a in parse_list(v, delim)],
                issues)
            new_columns.append(pl.Series(name, conv, dtype=pl.List(pl.Utf8)))

        elif kind is FieldKind.AMOUNT_LIST:
            conv = []
            for idx, value in zip(indices, values):
                if _is_blank(value):
                    issues.add(idx, name, IssueCode.MISSING_VALUE)
                    conv.append(None)
                    continue
                try:
                    conv.append(_normalize_amount_list(value, delim, idx, name, issues))
                except (ValueError, TypeError, SyntaxError):
                    issues.add(idx, name, IssueCode.INVALID_NUMBER, f"value={_short(value)}")
                    conv.append(None)
            new_columns.append(pl.Series(name, conv, dtype=pl.List(pl.Float64)))

        elif kind is FieldKind.NUMBER:
            conv = _convert_column(values, indices, name, IssueCode.INVALID_NUMBER,
                                   parse_number, issues)
            for idx, number in zip(indices, conv):
                if number is not None and number < 0:
                    issues.add(idx, name, IssueCode.NEGATIVE_AMOUNT)
            new_columns.append(pl.Series(name, conv, dtype=pl.Float64))

        elif kind is FieldKind.CATEGORY:
            conv = []
            for idx, value in zip(indices, values):
                if _is_blank(value):
                    issues.add(idx, name, IssueCode.MISSING_VALUE)
                    conv.append(None)
                else:
                    conv.append(str(value).strip())
            new_columns.append(pl.Series(name, conv, dtype=pl.Utf8))

    logger.info("Normalized %d canonical columns; %d issues recorded",
                len(new_columns), len(issues.rows))
    return NormalizationResult(frame=frame.with_columns(new_columns), issues=issues)
