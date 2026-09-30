import polars as pl
import pytest

from app.storage.duckdb_store import DuckDBStore
from app.storage.parquet_store import ParquetStore


def test_parquet_roundtrip_keeps_types(tmp_path):
    store = ParquetStore(tmp_path)
    frame = pl.DataFrame({"a": [1, 2], "l": [["x"], ["y", "z"]]})
    store.write("t1", frame)
    assert store.exists("t1")
    assert store.read("t1").equals(frame)
    assert store.scan("t1").filter(pl.col("a") == 2).collect().height == 1
    assert store.list_tables() == ["t1"]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("bad", ["../x", "a b", "1abc", "t;drop"])
def test_parquet_rejects_bad_names(tmp_path, bad):
    with pytest.raises(ValueError):
        ParquetStore(tmp_path).path_for(bad)


def test_duckdb_schema_and_runs(tmp_path):
    with DuckDBStore(tmp_path / "db.duckdb") as db:
        db.init_schema()
        db.init_schema()  # idempotent
        assert db.ping()
        run = db.start_run("file.csv", "abc")
        db.save_validation_report(run, {"records_received": 3})
        db.finish_run(run)
        runs = db.list_runs()
        assert runs.height == 1 and runs["status"][0] == "completed"


def test_duckdb_write_table_and_parquet_view(tmp_path):
    frame = pl.DataFrame({"k": ["a", "b"], "v": [1.5, 2.5]})
    ParquetStore(tmp_path).write("feat", frame)
    with DuckDBStore(tmp_path / "db.duckdb") as db:
        db.write_table("t", frame)
        assert db.table_exists("t")
        assert db.query("SELECT sum(v) AS s FROM t")["s"][0] == 4.0
        db.register_parquet_view("feat_view", tmp_path / "feat.parquet")
        assert db.query("SELECT k FROM feat_view WHERE v > ?", [2])["k"].to_list() == ["b"]
        with pytest.raises(ValueError):
            db.write_table("bad name", frame)
