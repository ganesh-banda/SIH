"""Parquet read/write helpers.

Writes are atomic (write to a temp file, then rename) so a crash never leaves
a half-written table that later code would read as valid.
Files are only written under the configured base directory.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ParquetStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        if not _NAME.match(name):
            raise ValueError(f"Invalid table name: {name!r}")
        return self.base_dir / f"{name}.parquet"

    def write(self, name: str, frame: pl.DataFrame, compression: str = "zstd") -> Path:
        target = self.path_for(name)
        tmp = target.with_suffix(".parquet.tmp")
        frame.write_parquet(tmp, compression=compression)
        os.replace(tmp, target)
        logger.info("Parquet written: %s (%d rows)", target.name, frame.height)
        return target

    def read(self, name: str, columns: list[str] | None = None) -> pl.DataFrame:
        return pl.read_parquet(self.path_for(name), columns=columns)

    def scan(self, name: str) -> pl.LazyFrame:
        """Lazy scan: only reads what the query needs (good for large tables)."""
        return pl.scan_parquet(self.path_for(name))

    def exists(self, name: str) -> bool:
        return self.path_for(name).is_file()

    def list_tables(self) -> list[str]:
        return sorted(p.stem for p in self.base_dir.glob("*.parquet"))
