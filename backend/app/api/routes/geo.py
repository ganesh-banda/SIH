"""Local GeoLite2 lookup endpoint (no online geolocation)."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_geo_service
from app.api.schemas import GeoLookupResponse
from app.preprocessing.ip_geolocation import GeoIPService

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/ip/{ip}", response_model=GeoLookupResponse)
def lookup_ip(ip: str, geo: GeoIPService = Depends(get_geo_service)) -> GeoLookupResponse:
    """Classify and (if public) geolocate one IP. Never fails on bad input."""
    return GeoLookupResponse(**geo.lookup(ip).to_dict())


@router.get("/status")
def geo_status(geo: GeoIPService = Depends(get_geo_service)) -> dict:
    return geo.status()
