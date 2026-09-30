"""Shared fixtures. Nothing here is modelled on the official dataset."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from geoip2.errors import AddressNotFoundError

from app.config import Settings
from app.ingestion.schema_mapping import SchemaMapping


# --- fake GeoLite readers (same interface as geoip2.database.Reader) -------

def _city_response(country, iso, region, city, lat, lon, tz):
    return SimpleNamespace(
        country=SimpleNamespace(name=country, iso_code=iso),
        subdivisions=[SimpleNamespace(name=region)] if region else [],
        city=SimpleNamespace(name=city),
        location=SimpleNamespace(latitude=lat, longitude=lon, accuracy_radius=50, time_zone=tz),
    )


class FakeCityReader:
    def __init__(self, table: dict):
        self.table = table
        self.calls = 0

    def city(self, ip):
        self.calls += 1
        if ip not in self.table:
            raise AddressNotFoundError(f"{ip} not in database")
        return _city_response(*self.table[ip])


class FakeASNReader:
    def __init__(self, table: dict):
        self.table = table
        self.calls = 0

    def asn(self, ip):
        self.calls += 1
        if ip not in self.table:
            raise AddressNotFoundError(f"{ip} not in database")
        number, org = self.table[ip]
        return SimpleNamespace(autonomous_system_number=number,
                               autonomous_system_organization=org)


@pytest.fixture
def fake_city_reader():
    return FakeCityReader({
        "8.8.8.8": ("United States", "US", "California", "Mountain View",
                    37.4, -122.1, "America/Los_Angeles"),
        "1.1.1.1": ("Australia", "AU", None, None, -33.5, 151.0, "Australia/Sydney"),
    })


@pytest.fixture
def fake_asn_reader():
    return FakeASNReader({"8.8.8.8": (15169, "GOOGLE")})


# --- a generic mapping where raw column names == canonical names ------------

@pytest.fixture
def identity_mapping() -> SchemaMapping:
    names = ["timestamp", "src_ip", "dst_ip", "src_port", "dst_port", "txid",
             "input_addresses", "output_addresses", "input_amounts", "output_amounts", "fee"]
    return SchemaMapping(fields={n: n for n in names}, required_fields=["txid", "timestamp"],
                         list_delimiter=";")


# --- isolated settings + API client ---------------------------------------

@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed",
        features_dir=tmp_path / "features", results_dir=tmp_path / "results",
        models_dir=tmp_path / "models", logs_dir=tmp_path / "logs",
        duckdb_path=tmp_path / "results" / "test.duckdb",
        schema_mapping_path=tmp_path / "missing_mapping.json",
        geolite_city_db=tmp_path / "no-city.mmdb", geolite_asn_db=tmp_path / "no-asn.mmdb",
        use_synthetic_geo=False,
        log_to_file=False,
    )


@pytest.fixture
def client(test_settings: Settings):
    from app.main import create_app

    with TestClient(create_app(test_settings)) as c:
        yield c
