"""FastAPI dependencies: access to shared services stored on app.state."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.preprocessing.ip_geolocation import GeoIPService
from app.storage.duckdb_store import DuckDBStore


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_geo_service(request: Request) -> GeoIPService:
    return request.app.state.geo


def get_store(request: Request) -> DuckDBStore:
    return request.app.state.store
