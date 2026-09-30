"""CSV parser.

Every column is read as a string. Type conversion happens later in the
normalizer, where failures are *recorded* instead of silently turning into
nulls at read time. This keeps what we loaded identical to what is on disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


def parse_csv(path: Path, separator: str = ",", encoding: str = "utf8") -> pl.DataFrame:
    """Read a CSV file with all columns as strings.

    Rows with the wrong number of fields raise an error rather than being
    dropped; ``truncate_ragged_lines`` is deliberately left off.
    """
    frame = pl.read_csv(
        path,
        separator=separator,
        infer_schema=False,  # all Utf8
        encoding=encoding,
        missing_utf8_is_empty_string=False,
    )
    logger.info("CSV parsed: %s (%d rows, %d columns)", path.name, frame.height, frame.width)
    return frame
