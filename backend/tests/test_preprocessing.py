from datetime import datetime, timezone

import polars as pl
import pytest

from app.ingestion.loader import load_dataset
from app.ingestion.schema_mapping import RECORD_INDEX_COL
from app.preprocessing.issues import IssueCollector
from app.preprocessing.normalizer import (
    normalize, normalize_address, normalize_txid, parse_list, parse_port, parse_timestamp,
)
from app.preprocessing.pipeline import preprocess
from app.preprocessing.validator import validate

HEX = "a" * 64


# --- scalar helpers --------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("2024-01-02T03:04:05Z", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
    ("2024-01-02 03:04:05", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
    ("2024-01-02T08:34:05+05:30", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
    ("1704164645", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
    ("1704164645000", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
    (1704164645, datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
])
def test_parse_timestamp(value, expected):
    assert parse_timestamp(value) == expected


def test_parse_timestamp_explicit_unit_and_errors():
    assert parse_timestamp("1704164645000", unit="ms").year == 2024
    with pytest.raises(ValueError):
        parse_timestamp("yesterday")
    with pytest.raises(ValueError):
        parse_timestamp("2024-01-02T03:04:05", naive_is_utc=False)


def test_parse_list_forms():
    assert parse_list(["a"]) == ["a"]
    assert parse_list('["a", "b"]') == ["a", "b"]
    assert parse_list("['a', 'b']") == ["a", "b"]
    assert parse_list("a; b", delimiter=";") == ["a", "b"]
    assert parse_list("single") == ["single"]


def test_port():
    assert parse_port("8333") == 8333
    for bad in ("70000", "-1", "1.5", "x"):
        with pytest.raises(ValueError):
            parse_port(bad)


def test_address_normalization():
    assert normalize_address("  BC1QABC ") == "bc1qabc"          # bech32 -> lower
    assert normalize_address("1BoatSLRHtKNngkdXEeobR76b53LETtpyT") == \
        "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"                    # base58 case kept
    with pytest.raises(ValueError):
        normalize_address("   ")


def test_txid_normalization():
    assert normalize_txid("  " + "A" * 64) == ("a" * 64, True)
    assert normalize_txid("tx_001") == ("tx_001", False)


# --- end-to-end normalize + validate on a tiny generic CSV ------------------

CSV = (
    "timestamp,src_ip,dst_ip,src_port,dst_port,txid,input_addresses,output_addresses,"
    "input_amounts,output_amounts,fee\n"
    f"2024-01-01T00:00:00Z,8.8.8.8,10.0.0.1,8333,8333,{HEX},w1;w2,w3,1.0;2.0,2.9,0.1\n"
    f"not-a-date,999.1.1.1,1.1.1.1,99999,8333,{HEX},w1,w4,1.0,0.9,0.1\n"   # bad ts/ip/port
    ",8.8.8.8,1.1.1.1,1,2,,w5,w6,1,1,0\n"                                  # missing required
    "2024-01-01T00:00:00Z,8.8.8.8,1.1.1.1,1,2,tx_2,w7;w8,w9,5.0,4.0,-1\n"   # mismatch + neg fee
    "2024-01-01T00:00:00Z,8.8.8.8,1.1.1.1,1,2,tx_2,w7;w8,w9,5.0,4.0,-1\n"   # exact duplicate
)


@pytest.fixture
def processed(tmp_path, identity_mapping):
    p = tmp_path / "d.csv"
    p.write_text(CSV)
    return preprocess(load_dataset(p), identity_mapping)


def _issues_for(result, idx):
    return set(result.issues.filter(pl.col("record_index") == idx)["code"].to_list())


def test_no_rows_are_dropped(processed):
    assert processed.frame.height == 5
    assert processed.frame[RECORD_INDEX_COL].to_list() == [0, 1, 2, 3, 4]


def test_types_after_normalization(processed):
    f = processed.frame
    assert f.schema["timestamp"] == pl.Datetime("us", "UTC")
    assert f.schema["input_addresses"] == pl.List(pl.Utf8)
    assert f.schema["input_amounts"] == pl.List(pl.Float64)
    assert f["input_addresses"][0].to_list() == ["w1", "w2"]
    assert f["src_ip_category"].to_list()[:2] == ["public", "invalid"]


def test_clean_row_is_valid(processed):
    row = processed.frame.row(0, named=True)
    assert row["_is_valid"] and not row["_is_duplicate"]
    assert "NON_PUBLIC_IP" in row["_issue_codes"]  # info only


def test_bad_values_flagged(processed):
    codes = _issues_for(processed, 1)
    assert {"INVALID_TIMESTAMP", "INVALID_IP", "INVALID_PORT"} <= codes
    # timestamp is required -> error -> invalid
    assert processed.frame.row(1, named=True)["_is_valid"] is False


def test_missing_required_is_invalid(processed):
    assert processed.frame.row(2, named=True)["_is_valid"] is False
    assert "MISSING_VALUE" in _issues_for(processed, 2)


def test_structural_problems(processed):
    codes = _issues_for(processed, 3)
    assert {"LIST_LENGTH_MISMATCH", "NEGATIVE_AMOUNT", "INVALID_TXID_FORMAT"} <= codes


def test_duplicates_flagged_not_removed(processed):
    f = processed.frame
    assert f["_is_duplicate"].to_list() == [False, False, False, False, True]
    assert "DUPLICATE_RECORD" in _issues_for(processed, 4)


def test_duplicate_txid_across_distinct_records(processed):
    # rows 0 and 1 share a txid (row 4 is an exact copy of 3, so tx_2 is not repeated)
    assert "DUPLICATE_TXID" in _issues_for(processed, 0)
    assert processed.report.duplicate_txid_values == 1


def test_report(processed):
    r = processed.report
    assert r.records_received == 5
    assert r.valid_records + r.invalid_records == 5
    assert r.duplicate_records == 1
    assert r.invalid_ips == 1
    assert r.missing_by_field.get("timestamp") == 1


def test_json_lists_handled(tmp_path):
    import json
    from app.ingestion.schema_mapping import SchemaMapping
    mapping = SchemaMapping(fields={n: n for n in
                                    ("txid", "timestamp", "input_addresses", "input_amounts")})
    p = tmp_path / "d.json"
    p.write_text(json.dumps([{"txid": HEX, "timestamp": 1704164645,
                              "input_addresses": ["w1", "w2"], "input_amounts": [1, 2]}]))
    res = preprocess(load_dataset(p), mapping)
    assert res.frame["input_amounts"][0].to_list() == [1.0, 2.0]
    assert res.frame.row(0, named=True)["_is_valid"]


def test_validate_empty_issue_collector():
    frame = pl.DataFrame({"txid": ["a"]}).with_row_index(RECORD_INDEX_COL)
    from app.ingestion.schema_mapping import SchemaMapping
    res = validate(frame, IssueCollector(), SchemaMapping(fields={"txid": "txid"}))
    assert res.frame["_is_valid"].to_list() == [True]
    assert res.frame["_issue_codes"].to_list() == [[]]
