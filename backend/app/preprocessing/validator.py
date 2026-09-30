"""Record validation and data-quality reporting.

Runs after ``normalize``. Adds structural checks, decides severity, and
flags rows. It never removes rows. Output columns added to the frame:

    _is_valid      -> False if the record has any ERROR-severity issue
    _is_duplicate  -> True for 2nd+ copies of an identical record
    _issue_codes   -> list of issue codes for that record (for quick filtering)

The full issue list is returned separately and should be stored alongside
the processed data.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import polars as pl

from app.ingestion.schema_mapping import RECORD_INDEX_COL, SchemaMapping
from app.preprocessing.issues import (
    UPGRADE_WHEN_REQUIRED, IssueCode, IssueCollector, Severity,
)

logger = logging.getLogger(__name__)

# (addresses column, amounts column) pairs that must have equal lengths.
LIST_PAIRS = (("input_addresses", "input_amounts"), ("output_addresses", "output_amounts"))


@dataclass
class ValidationReport:
    records_received: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    duplicate_txid_values: int
    missing_by_field: dict[str, int] = field(default_factory=dict)
    invalid_ips: int = 0
    non_public_ips: int = 0
    issue_counts: dict[str, int] = field(default_factory=dict)
    severity_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationResult:
    frame: pl.DataFrame
    issues: pl.DataFrame
    report: ValidationReport


def _check_list_lengths(frame: pl.DataFrame, issues: IssueCollector) -> None:
    for addr_col, amt_col in LIST_PAIRS:
        if addr_col not in frame.columns or amt_col not in frame.columns:
            continue
        mismatched = frame.filter(
            pl.col(addr_col).is_not_null() & pl.col(amt_col).is_not_null()
            & (pl.col(addr_col).list.len() != pl.col(amt_col).list.len())
        )
        for row in mismatched.select(RECORD_INDEX_COL, addr_col, amt_col).iter_rows():
            issues.add(row[0], f"{addr_col}/{amt_col}", IssueCode.LIST_LENGTH_MISMATCH,
                       f"{len(row[1])} addresses vs {len(row[2])} amounts")


def _flag_duplicates(frame: pl.DataFrame, issues: IssueCollector) -> pl.Series:
    """Mark every copy after the first of an exact duplicate record."""
    content = frame.drop(RECORD_INDEX_COL)
    if content.width == 0:
        return pl.Series("_is_duplicate", [False] * frame.height)
    dup_series = content.select(
        (~pl.struct(pl.all()).is_first_distinct()).alias("_is_duplicate")
    ).to_series()
    for idx in frame.filter(dup_series).get_column(RECORD_INDEX_COL).to_list():
        issues.add(idx, None, IssueCode.DUPLICATE_RECORD)
    return dup_series


def _flag_duplicate_txids(frame: pl.DataFrame, duplicates: pl.Series,
                          issues: IssueCollector) -> int:
    """Flag TXIDs that appear in more than one (non-identical) record."""
    if "txid" not in frame.columns:
        return 0
    distinct = frame.filter(~duplicates & pl.col("txid").is_not_null())
    counts = distinct.group_by("txid").len()
    repeated = counts.filter(pl.col("len") > 1)
    if repeated.height == 0:
        return 0
    rows = distinct.join(repeated, on="txid").select(RECORD_INDEX_COL, "len")
    for idx, n in rows.iter_rows():
        issues.add(idx, "txid", IssueCode.DUPLICATE_TXID, f"txid appears in {n} records")
    return repeated.height


def _apply_required_severity(issues: pl.DataFrame, required: list[str]) -> pl.DataFrame:
    upgrade = [c.value for c in UPGRADE_WHEN_REQUIRED]
    return issues.with_columns(
        pl.when(pl.col("field").is_in(required) & pl.col("code").is_in(upgrade))
        .then(pl.lit(Severity.ERROR.value))
        .otherwise(pl.col("severity"))
        .alias("severity")
    )


def validate(frame: pl.DataFrame, normalization_issues: IssueCollector,
             mapping: SchemaMapping) -> ValidationResult:
    """Run structural checks and produce flags plus a validation report."""
    issues = IssueCollector()
    issues.extend(normalization_issues)
    _check_list_lengths(frame, issues)
    duplicates = _flag_duplicates(frame, issues)
    dup_txids = _flag_duplicate_txids(frame, duplicates, issues)

    issue_frame = _apply_required_severity(issues.to_frame(), mapping.required_fields)

    per_record = issue_frame.group_by("record_index").agg(
        pl.col("code").unique().sort().alias("_issue_codes"),
        (pl.col("severity") == Severity.ERROR.value).any().alias("_has_error"),
    ).rename({"record_index": RECORD_INDEX_COL})

    flagged = (
        frame.with_columns(duplicates)
        .join(per_record, on=RECORD_INDEX_COL, how="left")
        .with_columns(
            (~pl.col("_has_error").fill_null(False)).alias("_is_valid"),
            pl.col("_issue_codes").fill_null(pl.lit([], dtype=pl.List(pl.Utf8))),
        )
        .drop("_has_error")
        .sort(RECORD_INDEX_COL)
    )

    report = _build_report(flagged, issue_frame, dup_txids)
    logger.info(
        "Validation: %d received, %d valid, %d invalid, %d duplicates",
        report.records_received, report.valid_records,
        report.invalid_records, report.duplicate_records,
    )
    return ValidationResult(frame=flagged, issues=issue_frame, report=report)


def _counts(frame: pl.DataFrame, column: str) -> dict[str, int]:
    if frame.height == 0:
        return {}
    return dict(frame.group_by(column).len().sort(column).iter_rows())


def _build_report(frame: pl.DataFrame, issues: pl.DataFrame, dup_txids: int) -> ValidationReport:
    missing = issues.filter(pl.col("code") == IssueCode.MISSING_VALUE.value)
    return ValidationReport(
        records_received=frame.height,
        valid_records=int(frame.get_column("_is_valid").sum()),
        invalid_records=int((~frame.get_column("_is_valid")).sum()),
        duplicate_records=int(frame.get_column("_is_duplicate").sum()),
        duplicate_txid_values=dup_txids,
        missing_by_field=_counts(missing, "field"),
        invalid_ips=issues.filter(pl.col("code") == IssueCode.INVALID_IP.value).height,
        non_public_ips=issues.filter(pl.col("code") == IssueCode.NON_PUBLIC_IP.value).height,
        issue_counts=_counts(issues, "code"),
        severity_counts=_counts(issues, "severity"),
    )
