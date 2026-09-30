"""DuckDB access layer.

DuckDB is an embedded, file-based analytical database: no server, fully
offline. It is used for:

* dataset-independent metadata tables created here (analysis runs,
  validation reports),
* querying Parquet files through views (no data copy),
* storing result tables written by later pipeline stages.

Dataset-specific tables (transactions, wallets, features, risk_scores, ...)
are NOT created here. TODO(dataset): define them after schema mapping.

Only identifiers matching a strict pattern are ever interpolated into SQL;
values always go through parameters.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

logger = logging.getLogger(__name__)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

METADATA_DDL = (
    """
    CREATE TABLE IF NOT EXISTS analysis_runs (
        run_id        VARCHAR PRIMARY KEY,
        started_at    TIMESTAMPTZ NOT NULL,
        finished_at   TIMESTAMPTZ,
        status        VARCHAR NOT NULL,
        source_file   VARCHAR,
        source_sha256 VARCHAR,
        notes         VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_reports (
        run_id      VARCHAR NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL,
        report_json VARCHAR NOT NULL
    )
    """,
)


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


class DuckDBStore:
    """Thin wrapper around a single DuckDB file.

    One connection is shared; a lock serialises access because DuckDB
    connections are not safe to use from several threads at once (FastAPI
    runs sync endpoints in a thread pool).
    """

    def __init__(self, db_path: Path, read_only: bool = False) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.db_path), read_only=read_only)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DuckDBStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- setup -----------------------------------------------------------
    def init_schema(self) -> None:
        with self._lock:
            for ddl in METADATA_DDL:
                self._conn.execute(ddl)
        logger.info("DuckDB metadata schema ready at %s", self.db_path.name)

    def ping(self) -> bool:
        try:
            with self._lock:
                return self._conn.execute("SELECT 1").fetchone() == (1,)
        except duckdb.Error:
            return False

    # --- generic ---------------------------------------------------------
    def query(self, sql: str, params: list[Any] | None = None) -> pl.DataFrame:
        with self._lock:
            return self._conn.execute(sql, params or []).pl()

    def write_table(self, name: str, frame: pl.DataFrame, replace: bool = True) -> None:
        """Store a Polars frame as a DuckDB table (via Arrow, zero-copy)."""
        table = _check_ident(name)
        arrow = frame.to_arrow()
        with self._lock:
            self._conn.register("_incoming", arrow)
            try:
                verb = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"
                self._conn.execute(f"{verb} {table} AS SELECT * FROM _incoming")
            finally:
                self._conn.unregister("_incoming")
        logger.info("DuckDB table written: %s (%d rows)", table, frame.height)

    def register_parquet_view(self, name: str, parquet_path: Path) -> None:
        """Expose a Parquet file as a view without copying the data."""
        view = _check_ident(name)
        path = str(Path(parquet_path).resolve()).replace("'", "''")
        with self._lock:
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{path}')"
            )

    def table_exists(self, name: str) -> bool:
        _check_ident(name)
        with self._lock:
            row = self._conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
            ).fetchone()
        return bool(row and row[0])

    # --- analysis runs ---------------------------------------------------
    def start_run(self, source_file: str | None = None, source_sha256: str | None = None,
                  notes: str | None = None) -> str:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO analysis_runs VALUES (?, ?, NULL, 'running', ?, ?, ?)",
                [run_id, datetime.now(timezone.utc), source_file, source_sha256, notes],
            )
        logger.info("Analysis run started: %s", run_id)
        return run_id

    def finish_run(self, run_id: str, status: str = "completed") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE analysis_runs SET finished_at = ?, status = ? WHERE run_id = ?",
                [datetime.now(timezone.utc), status, run_id],
            )
        logger.info("Analysis run %s finished with status %s", run_id, status)

    def save_validation_report(self, run_id: str, report: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO validation_reports VALUES (?, ?, ?)",
                [run_id, datetime.now(timezone.utc), json.dumps(report)],
            )

    def list_runs(self, limit: int = 20) -> pl.DataFrame:
        return self.query(
            "SELECT * FROM analysis_runs ORDER BY started_at DESC LIMIT ?", [limit]
        )
