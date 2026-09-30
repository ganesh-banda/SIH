"""Read persisted analysis tables without rebuilding the graph or models."""
from __future__ import annotations

import json
from fastapi import HTTPException
from app.storage.duckdb_store import DuckDBStore


def rows(store: DuckDBStore, sql: str, params: list | None = None) -> list[dict]:
    try:
        return store.query(sql, params).to_dicts()
    except Exception as exc:
        if not store.table_exists("transactions"):
            raise HTTPException(503, "Analysis has not been run") from exc
        raise


def one(store: DuckDBStore, sql: str, params: list | None = None) -> dict:
    found = rows(store, sql, params)
    if not found:
        raise HTTPException(404, "Record not found")
    return found[0]


def decode(record: dict, *keys: str) -> dict:
    for key in keys:
        if isinstance(record.get(key), str):
            record[key] = json.loads(record[key])
    return record
