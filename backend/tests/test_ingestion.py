import json

import pytest

from app.ingestion.json_parser import JSONLayoutError, flatten_record
from app.ingestion.loader import UnsupportedFormatError, load_dataset
from app.ingestion.schema_mapping import (
    RECORD_INDEX_COL, SchemaMapping, SchemaMappingError, apply_mapping,
)


def test_csv_reads_everything_as_strings(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("a,b,c\n1,x,0.5\n2,,007\n")
    res = load_dataset(p)
    assert res.file_format == "csv"
    assert res.row_count == 2
    assert res.frame["c"].to_list() == ["0.5", "007"]  # leading zeros preserved
    assert res.frame["b"].to_list() == ["x", None]
    assert res.frame[RECORD_INDEX_COL].to_list() == [0, 1]
    assert len(res.sha256) == 64


def test_raw_file_is_not_modified(tmp_path):
    p = tmp_path / "d.csv"
    content = "a,b\n1,2\n"
    p.write_text(content)
    load_dataset(p)
    assert p.read_text() == content


def test_json_array_with_nested_and_lists(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps([{"id": 1, "net": {"ip": "8.8.8.8"}, "items": ["a", "b"]},
                             {"id": 2, "net": {"ip": "1.1.1.1"}, "items": ["c"]}]))
    res = load_dataset(p)
    assert set(res.frame.columns) >= {"id", "net.ip", "items"}
    assert res.frame["items"].to_list() == [["a", "b"], ["c"]]


def test_json_wrapped_object(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"meta": "x", "records": [{"a": 1}, {"a": 2}]}))
    assert load_dataset(p).row_count == 2


def test_json_ambiguous_wrapper_rejected(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"x": [{"a": 1}], "y": [{"a": 2}]}))
    with pytest.raises(JSONLayoutError):
        load_dataset(p)


def test_jsonl_with_late_new_field(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"a": 1}\n\n{"a": 2, "b": "late"}\n')
    res = load_dataset(p)
    assert res.row_count == 2
    assert res.frame["b"].to_list() == [None, "late"]


def test_jsonl_bad_line_reports_line_number(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"a": 1}\n{oops\n')
    with pytest.raises(JSONLayoutError, match="line 2"):
        load_dataset(p)


def test_xml_records_attributes_and_repeated_tags(tmp_path):
    p = tmp_path / "d.xml"
    p.write_text(
        "<root>"
        "<rec id='1'><a>x</a><inputs><addr>w1</addr><addr>w2</addr></inputs></rec>"
        "<rec id='2'><a>y</a><inputs><addr>w3</addr></inputs></rec>"
        "</root>")
    res = load_dataset(p)
    assert res.row_count == 2
    assert res.frame["id"].to_list() == ["1", "2"]
    assert res.frame["a"].to_list() == ["x", "y"]
    # the single <addr> in record 2 is still a list
    assert res.frame["inputs.addr"].to_list() == [["w1", "w2"], ["w3"]]


def test_xml_explicit_record_tag(tmp_path):
    p = tmp_path / "d.xml"
    p.write_text("<root><header><v>1</v></header><item><a>1</a></item><item><a>2</a></item></root>")
    assert load_dataset(p, xml_record_tag="item").row_count == 2


def test_unsupported_format(tmp_path):
    p = tmp_path / "d.xlsx"
    p.write_bytes(b"x")
    with pytest.raises(UnsupportedFormatError):
        load_dataset(p)


def test_flatten_record():
    assert flatten_record({"a": {"b": {"c": 1}}, "l": [1]}) == {"a.b.c": 1, "l": [1]}


def test_mapping_rename_and_passthrough(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("TX,time,extra\nab,1,z\n")
    frame = load_dataset(p).frame
    m = SchemaMapping.from_dict({"fields": {"txid": "TX", "timestamp": "time"}})
    out = apply_mapping(frame, m)
    assert {"txid", "timestamp", "extra"} <= set(out.columns)


def test_mapping_errors(tmp_path):
    with pytest.raises(SchemaMappingError):
        SchemaMapping.from_dict({"fields": {"not_a_field": "x"}})
    with pytest.raises(SchemaMappingError):
        SchemaMapping.from_dict({"fields": {"txid": None}, "required_fields": ["txid"]})
    with pytest.raises(SchemaMappingError):
        SchemaMapping.from_dict({"fields": {"txid": "c", "fee": "c"}})
    with pytest.raises(SchemaMappingError, match="not found"):
        SchemaMapping.from_file(tmp_path / "missing.json")

    p = tmp_path / "d.csv"
    p.write_text("a\n1\n")
    frame = load_dataset(p).frame
    with pytest.raises(SchemaMappingError, match="no fields mapped"):
        apply_mapping(frame, SchemaMapping())
    with pytest.raises(SchemaMappingError, match="not found in dataset"):
        apply_mapping(frame, SchemaMapping(fields={"txid": "zzz"}))


def test_mapping_example_file_is_valid():
    from app.config import BACKEND_ROOT
    m = SchemaMapping.from_file(BACKEND_ROOT / "config" / "schema_mapping.example.json")
    assert m.mapped_fields == {}
