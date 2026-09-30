"""Health check: reports what is actually working, not just 'up'."""

from fastapi import APIRouter, Depends

from app import __version__
from app.api.dependencies import get_app_settings, get_geo_service, get_store
from app.api.schemas import ComponentStatus, HealthResponse
from app.config import Settings
from app.preprocessing.ip_geolocation import GeoIPService
from app.storage.duckdb_store import DuckDBStore

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_app_settings),
           geo: GeoIPService = Depends(get_geo_service),
           store: DuckDBStore = Depends(get_store)) -> HealthResponse:
    db_ok = store.ping()
    components = {
        "duckdb": ComponentStatus(ok=db_ok, detail=None if db_ok else "query failed"),
        "geolite_city": ComponentStatus(
            ok=geo.city_available and not geo.synthetic,
            detail="synthetic fixture active" if geo.synthetic else
                   (None if geo.city_available else f"not found: {settings.geolite_city_db.name}")),
        "geolite_asn": ComponentStatus(
            ok=geo.asn_available and not geo.synthetic,
            detail="synthetic fixture active" if geo.synthetic else
                   (None if geo.asn_available else f"not found: {settings.geolite_asn_db.name}")),
    }
    # GeoLite missing = degraded (the app still runs), DuckDB down = error.
    status = "ok" if all(c.ok for c in components.values()) else ("degraded" if db_ok else "error")
    return HealthResponse(
        status=status, app=settings.app_name, version=__version__,
        environment=settings.environment, components=components,
        schema_mapping_configured=settings.schema_mapping_path.is_file(),
    )
