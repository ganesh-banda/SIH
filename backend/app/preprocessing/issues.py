"""Data-quality issue tracking.

Problems are never fixed silently or dropped. Each one becomes a row in an
issues table ``(record_index, field, code, severity, detail)`` so an
investigator can always see why a record was flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import polars as pl


class Severity(str, Enum):
    ERROR = "error"      # record is marked invalid
    WARNING = "warning"  # record kept as valid, but worth attention
    INFO = "info"        # context only (e.g. private IP)


class IssueCode(str, Enum):
    MISSING_VALUE = "MISSING_VALUE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_NUMBER = "INVALID_NUMBER"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    INVALID_IP = "INVALID_IP"
    NON_PUBLIC_IP = "NON_PUBLIC_IP"
    INVALID_PORT = "INVALID_PORT"
    INVALID_TXID_FORMAT = "INVALID_TXID_FORMAT"
    INVALID_LIST = "INVALID_LIST"
    LIST_LENGTH_MISMATCH = "LIST_LENGTH_MISMATCH"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    DUPLICATE_TXID = "DUPLICATE_TXID"


# Default severity for each code.
BASE_SEVERITY: dict[IssueCode, Severity] = {
    IssueCode.MISSING_VALUE: Severity.WARNING,
    IssueCode.INVALID_TIMESTAMP: Severity.WARNING,
    IssueCode.INVALID_NUMBER: Severity.WARNING,
    IssueCode.NEGATIVE_AMOUNT: Severity.ERROR,
    IssueCode.INVALID_IP: Severity.WARNING,
    IssueCode.NON_PUBLIC_IP: Severity.INFO,
    IssueCode.INVALID_PORT: Severity.WARNING,
    # Synthetic data may use non-hex TXIDs such as "tx_001"; not an error.
    IssueCode.INVALID_TXID_FORMAT: Severity.WARNING,
    IssueCode.INVALID_LIST: Severity.WARNING,
    IssueCode.LIST_LENGTH_MISMATCH: Severity.ERROR,
    IssueCode.DUPLICATE_RECORD: Severity.WARNING,
    # In P2P observation data one TXID is legitimately seen many times
    # (relayed between peers), so this is a warning, not an error.
    IssueCode.DUPLICATE_TXID: Severity.WARNING,
}

# Codes that become ERROR when they affect a *required* field.
UPGRADE_WHEN_REQUIRED = {
    IssueCode.MISSING_VALUE, IssueCode.INVALID_TIMESTAMP, IssueCode.INVALID_NUMBER,
    IssueCode.INVALID_IP, IssueCode.INVALID_PORT, IssueCode.INVALID_LIST,
}

ISSUE_SCHEMA = {
    "record_index": pl.UInt32, "field": pl.Utf8, "code": pl.Utf8,
    "severity": pl.Utf8, "detail": pl.Utf8,
}


@dataclass
class IssueCollector:
    rows: list[dict] = field(default_factory=list)

    def add(self, record_index: int, field_name: str | None, code: IssueCode,
            detail: str | None = None, severity: Severity | None = None) -> None:
        self.rows.append({
            "record_index": record_index,
            "field": field_name,
            "code": code.value,
            "severity": (severity or BASE_SEVERITY[code]).value,
            "detail": detail,
        })

    def extend(self, other: "IssueCollector") -> None:
        self.rows.extend(other.rows)

    def to_frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.rows, schema=ISSUE_SCHEMA)
