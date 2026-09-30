"""Inspect a dataset file before writing the schema mapping.

Usage (from backend/):
    python -m scripts.inspect_dataset data/raw/<file> [--rows 5] [--xml-tag TAG]

Prints format, row count, columns, dtypes, null counts and a few sample rows.
Reads the file only; never modifies it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from app.ingestion.loader import load_dataset
from app.ingestion.schema_mapping import RECORD_INDEX_COL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--xml-tag", default=None)
    args = parser.parse_args()

    result = load_dataset(args.path, xml_record_tag=args.xml_tag)
    frame = result.frame.drop(RECORD_INDEX_COL)
    print(json.dumps(result.summary(), indent=2))
    print("\nNull counts:")
    print(frame.null_count())
    print(f"\nFirst {args.rows} rows:")
    with pl.Config(tbl_cols=-1, fmt_str_lengths=60):
        print(frame.head(args.rows))


if __name__ == "__main__":
    main()
