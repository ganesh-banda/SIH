"""Offline IP geolocation against local MaxMind GeoLite2 MMDB files.

No network access is ever made. The service:

* opens GeoLite2-City and GeoLite2-ASN readers if the files exist,
* only looks up *public* IPs (private/reserved/etc. are never geolocated),
* returns an explicit ``lookup_status`` instead of raising,
* caches results per normalized IP (the same IP appears many times).

Geo information is CONTEXT, not evidence of wrongdoing. Nothing here assigns
risk; it only describes where an address is registered according to GeoLite.
GeoLite accuracy is limited (especially city-level), so downstream code
should treat these values as approximate.
"""

from __future__ import annotations

import logging
import csv
from dataclasses import asdict, dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Protocol

import polars as pl

from app.preprocessing.ip_validation import IPCategory, classify_ip

logger = logging.getLogger(__name__)


class LookupStatus(str, Enum):
    OK = "ok"                        # found in every available database
    PARTIAL = "partial"              # found in one DB but not the other
    NOT_FOUND = "not_found"          # public IP, but absent from GeoLite
    NOT_PUBLIC = "not_public"        # private/reserved/etc.: not geolocated
    INVALID = "invalid"              # malformed IP
    DB_UNAVAILABLE = "db_unavailable"  # no GeoLite database loaded


@dataclass(frozen=True)
class GeoResult:
    ip: str | None
    ip_category: str
    lookup_status: str
    country: str | None = None
    country_iso: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    accuracy_radius_km: int | None = None
    timezone: str | None = None
    asn: int | None = None
    asn_org: str | None = None
    data_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


GEO_RESULT_SCHEMA: dict[str, pl.DataType] = {
    "ip": pl.Utf8, "ip_category": pl.Utf8, "lookup_status": pl.Utf8,
    "country": pl.Utf8, "country_iso": pl.Utf8, "region": pl.Utf8, "city": pl.Utf8,
    "latitude": pl.Float64, "longitude": pl.Float64, "accuracy_radius_km": pl.Int64,
    "timezone": pl.Utf8, "asn": pl.Int64, "asn_org": pl.Utf8,
    "data_source": pl.Utf8,
}


class SyntheticCityReader:
    """CSV-backed fixture with the same response shape used by geoip2."""
    synthetic = True

    def __init__(self, path: Path) -> None:
        with path.open(newline="", encoding="utf-8") as handle:
            rows=list(csv.DictReader(handle))
        self.rows={r["ip"]:r for r in rows}
        if len(self.rows)!=len(rows): raise ValueError("Duplicate IP in synthetic City CSV")

    def city(self, ip_address: str) -> Any:
        r=self.rows[ip_address]
        return SimpleNamespace(
            country=SimpleNamespace(name=r["country"],iso_code=r["country_iso"]),
            subdivisions=[SimpleNamespace(name=r["region"])] if r["region"] else [],
            city=SimpleNamespace(name=r["city"]),
            location=SimpleNamespace(latitude=float(r["latitude"]) if r["latitude"] else None,
                longitude=float(r["longitude"]) if r["longitude"] else None,
                accuracy_radius=None,time_zone=r["timezone"] or None))


class SyntheticASNReader:
    synthetic = True

    def __init__(self, path: Path) -> None:
        with path.open(newline="", encoding="utf-8") as handle:
            rows=list(csv.DictReader(handle))
        self.rows={r["ip"]:r for r in rows}
        if len(self.rows)!=len(rows): raise ValueError("Duplicate IP in synthetic ASN CSV")

    def asn(self, ip_address: str) -> Any:
        r=self.rows[ip_address]
        return SimpleNamespace(autonomous_system_number=int(r["asn"]),
                               autonomous_system_organization=r["asn_org"])


class CityReader(Protocol):
    def city(self, ip_address: str) -> Any: ...


class ASNReader(Protocol):
    def asn(self, ip_address: str) -> Any: ...


def _open_reader(path: Path, label: str) -> Any | None:
    """Open an MMDB file if present; log and return None otherwise."""
    if not path.is_file():
        logger.warning("GeoLite2 %s database not found at %s; %s lookups disabled",
                       label, path, label)
        return None
    import geoip2.database  # imported lazily so tests can run without it

    reader = geoip2.database.Reader(str(path))
    logger.info("GeoLite2 %s database loaded: %s (build %s)",
                label, path.name, reader.metadata().build_epoch)
    return reader


class GeoIPService:
    """Local GeoLite2 lookup with an LRU cache.

    Readers can be injected (useful in tests); otherwise they are opened from
    the configured paths. Either database may be missing; the service keeps
    working and reports what it could not do.
    """

    def __init__(
        self,
        city_reader: CityReader | None = None,
        asn_reader: ASNReader | None = None,
        cache_size: int = 200_000,
    ) -> None:
        self._city = city_reader
        self._asn = asn_reader
        self._cached_lookup = lru_cache(maxsize=cache_size or None)(self._lookup_uncached)

    @classmethod
    def from_paths(cls, city_db: Path, asn_db: Path, cache_size: int = 200_000) -> "GeoIPService":
        return cls(_open_reader(city_db, "City"), _open_reader(asn_db, "ASN"), cache_size)

    @classmethod
    def from_synthetic_csv(cls, city_csv: Path, asn_csv: Path,
                           cache_size: int = 200_000) -> "GeoIPService":
        if not city_csv.is_file() or not asn_csv.is_file():
            raise FileNotFoundError("Synthetic City and ASN CSV fixtures are required")
        return cls(SyntheticCityReader(city_csv), SyntheticASNReader(asn_csv), cache_size)

    # --- status ----------------------------------------------------------
    @property
    def city_available(self) -> bool:
        return self._city is not None

    @property
    def asn_available(self) -> bool:
        return self._asn is not None

    @property
    def synthetic(self) -> bool:
        return bool(getattr(self._city,"synthetic",False) or getattr(self._asn,"synthetic",False))

    def status(self) -> dict[str, Any]:
        info = self._cached_lookup.cache_info()
        return {
            "city_db_loaded": self.city_available,
            "asn_db_loaded": self.asn_available,
            "data_source": "synthetic_fixture" if self.synthetic else "geolite_mmdb",
            "cache_hits": info.hits,
            "cache_misses": info.misses,
            "cache_size": info.currsize,
        }

    def close(self) -> None:
        for reader in (self._city, self._asn):
            close = getattr(reader, "close", None)
            if callable(close):
                close()

    # --- lookups ---------------------------------------------------------
    def lookup(self, ip: str | None) -> GeoResult:
        """Look up one IP. Never raises for bad input."""
        info = classify_ip(ip)
        if info.category is IPCategory.INVALID:
            return GeoResult(ip=ip, ip_category=info.category.value,
                             lookup_status=LookupStatus.INVALID.value)
        # Cache on the normalized form so '::ffff:1.2.3.4' and '1.2.3.4' share an entry.
        return self._cached_lookup(info.normalized)

    def lookup_many(self, ips: Iterable[str | None]) -> pl.DataFrame:
        """Look up each *distinct* IP once and return a table keyed by ``ip``."""
        unique = {ip for ip in ips if ip is not None}
        rows = [self.lookup(ip).to_dict() | {"ip": ip} for ip in sorted(unique)]
        return pl.DataFrame(rows, schema=GEO_RESULT_SCHEMA)

    def _lookup_uncached(self, normalized_ip: str) -> GeoResult:
        category = classify_ip(normalized_ip).category
        if category is not IPCategory.PUBLIC:
            return GeoResult(ip=normalized_ip, ip_category=category.value,
                             lookup_status=LookupStatus.NOT_PUBLIC.value)
        if not (self.city_available or self.asn_available):
            return GeoResult(ip=normalized_ip, ip_category=category.value,
                             lookup_status=LookupStatus.DB_UNAVAILABLE.value)

        city_fields = self._city_fields(normalized_ip)
        asn_fields = self._asn_fields(normalized_ip)
        attempted = [x for x in (city_fields, asn_fields) if x is not _SKIPPED]
        found = [x for x in attempted if x is not None]

        if not found:
            status = LookupStatus.NOT_FOUND
        elif len(found) < 2:
            status = LookupStatus.PARTIAL
        else:
            status = LookupStatus.OK

        merged: dict[str, Any] = {}
        for part in found:
            merged.update(part)
        return GeoResult(ip=normalized_ip, ip_category=category.value,
                         lookup_status=status.value,
                         data_source="synthetic_fixture" if self.synthetic else "geolite_mmdb",
                         **merged)

    def _city_fields(self, ip: str) -> dict[str, Any] | None | object:
        if self._city is None:
            return _SKIPPED
        try:
            resp = self._city.city(ip)
        except Exception as exc:  # AddressNotFoundError or corrupt DB entry
            _log_miss("City", exc)
            return None
        # First-level subdivision = state/province; consistent across countries.
        subdivision = resp.subdivisions[0] if len(resp.subdivisions) else None
        return {
            "country": resp.country.name,
            "country_iso": resp.country.iso_code,
            "region": subdivision.name if subdivision else None,
            "city": resp.city.name,
            "latitude": resp.location.latitude,
            "longitude": resp.location.longitude,
            "accuracy_radius_km": resp.location.accuracy_radius,
            "timezone": resp.location.time_zone,
        }

    def _asn_fields(self, ip: str) -> dict[str, Any] | None | object:
        if self._asn is None:
            return _SKIPPED
        try:
            resp = self._asn.asn(ip)
        except Exception as exc:
            _log_miss("ASN", exc)
            return None
        return {
            "asn": resp.autonomous_system_number,
            "asn_org": resp.autonomous_system_organization,
        }


_SKIPPED = object()  # sentinel: database not loaded, so lookup not attempted


def _log_miss(db: str, exc: Exception) -> None:
    # AddressNotFoundError is normal; anything else deserves a warning.
    if type(exc).__name__ == "AddressNotFoundError":
        logger.debug("GeoLite2 %s: address not found", db)
    else:
        logger.warning("GeoLite2 %s lookup failed: %s", db, type(exc).__name__)


def geo_service_for_settings(settings) -> GeoIPService:
    """Prefer installed MMDBs; otherwise use explicit synthetic test mode."""
    if settings.geolite_city_db.is_file() or settings.geolite_asn_db.is_file():
        return GeoIPService.from_paths(settings.geolite_city_db,settings.geolite_asn_db,
                                       settings.geo_cache_size)
    if settings.use_synthetic_geo:
        return GeoIPService.from_synthetic_csv(settings.synthetic_city_csv,
                                               settings.synthetic_asn_csv,
                                               settings.geo_cache_size)
    return GeoIPService.from_paths(settings.geolite_city_db,settings.geolite_asn_db,
                                   settings.geo_cache_size)
