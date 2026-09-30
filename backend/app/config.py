"""Central configuration.

Every path and tunable lives here. Values come from environment variables
(prefix ``BTCRISK_``) or a ``.env`` file in the backend directory.
Relative paths are resolved against the backend root, so the app behaves the
same no matter which directory you launch it from.

Nothing in this file is dataset-specific. Risk thresholds are intentionally
``None`` until score calibration has been done on the real dataset.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BTCRISK_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    app_name: str = "Bitcoin Risk Detection Backend"
    environment: str = "development"
    log_level: str = "INFO"
    log_to_file: bool = True

    # --- Directories -------------------------------------------------------
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    features_dir: Path = Path("data/features")
    results_dir: Path = Path("data/results")
    models_dir: Path = Path("models")
    logs_dir: Path = Path("logs")

    # --- Storage -----------------------------------------------------------
    duckdb_path: Path = Path("data/results/analysis.duckdb")

    # --- Schema mapping (filled in once the dataset is inspected) ----------
    schema_mapping_path: Path = Path("config/schema_mapping.json")

    # --- GeoLite2 (local MMDB files, never an online API) -------------------
    geolite_city_db: Path = Path("data/geolite/GeoLite2-City.mmdb")
    geolite_asn_db: Path = Path("data/geolite/GeoLite2-ASN.mmdb")
    use_synthetic_geo: bool = False
    synthetic_city_csv: Path = Path("data/geolite/Synthetic-City.csv")
    synthetic_asn_csv: Path = Path("data/geolite/Synthetic-ASN.csv")
    geo_cache_size: int = Field(default=200_000, ge=0)

    # --- Graph -------------------------------------------------------------
    graph_backend: str = "networkx"  # "igraph" reserved for later if scale requires it

    # --- Risk (TODO: set only after calibration on the real dataset) -------
    risk_threshold_medium: float | None = None
    risk_threshold_high: float | None = None

    # --- API ---------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173",
                               "http://127.0.0.1:3000", "http://127.0.0.1:5173"]

    @field_validator(
        "data_dir", "raw_dir", "processed_dir", "features_dir", "results_dir",
        "models_dir", "logs_dir", "duckdb_path", "schema_mapping_path",
        "geolite_city_db", "geolite_asn_db",
        "synthetic_city_csv", "synthetic_asn_csv",
    )
    @classmethod
    def _resolve_relative(cls, value: Path) -> Path:
        """Resolve relative paths against the backend root."""
        return value if value.is_absolute() else (BACKEND_ROOT / value).resolve()

    def ensure_directories(self) -> None:
        """Create writable working directories. Never touches file contents."""
        for directory in (
            self.raw_dir, self.processed_dir, self.features_dir,
            self.results_dir, self.models_dir, self.logs_dir,
            self.duckdb_path.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (use as a FastAPI dependency)."""
    return Settings()
