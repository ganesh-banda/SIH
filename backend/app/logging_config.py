"""Logging configuration using the standard library only.

Modules obtain loggers with ``logging.getLogger(__name__)``. Log messages
should describe *what happened* (counts, file names, error types) and never
dump full records, wallet lists or datasets.
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    """Configure console (and optionally rotating file) logging."""
    handlers: dict[str, dict] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": level,
        }
    }
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "level": level,
            "filename": str(log_dir / "backend.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
        }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"standard": {"format": LOG_FORMAT}},
            "handlers": handlers,
            "root": {"level": level, "handlers": list(handlers)},
            # Third-party libraries are noisy at DEBUG.
            "loggers": {
                "urllib3": {"level": "WARNING"},
                "matplotlib": {"level": "WARNING"},
            },
        }
    )
