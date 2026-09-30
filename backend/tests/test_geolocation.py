import pytest

from app.config import get_settings
from app.preprocessing.geo_features import (
    cross_check_asn, cross_check_country, enrich_ip_columns, haversine_km,
)
from app.preprocessing.ip_geolocation import GeoIPService, LookupStatus

import polars as pl


@pytest.fixture
def service(fake_city_reader, fake_asn_reader):
    return GeoIPService(fake_city_reader, fake_asn_reader, cache_size=100)


def test_public_ip_found_in_both(service):
    r = service.lookup("8.8.8.8")
    assert r.lookup_status == LookupStatus.OK.value
    assert (r.country_iso, r.city, r.region, r.asn, r.asn_org) == (
        "US", "Mountain View", "California", 15169, "GOOGLE")
    assert r.timezone == "America/Los_Angeles"


def test_partial_when_only_city_has_it(service):
    r = service.lookup("1.1.1.1")
    assert r.lookup_status == LookupStatus.PARTIAL.value
    assert r.country_iso == "AU" and r.asn is None and r.region is None


def test_public_ip_missing_from_geolite(service):
    r = service.lookup("9.9.9.9")
    assert r.lookup_status == LookupStatus.NOT_FOUND.value
    assert r.country is None


@pytest.mark.parametrize("ip", ["10.0.0.1", "172.16.5.4", "192.168.1.1", "127.0.0.1",
                                "::1", "fc00::1", "203.0.113.9"])
def test_non_public_ips_are_never_looked_up(service, fake_city_reader, ip):
    r = service.lookup(ip)
    assert r.lookup_status == LookupStatus.NOT_PUBLIC.value
    assert fake_city_reader.calls == 0


def test_malformed_ip(service):
    r = service.lookup("not-an-ip")
    assert r.lookup_status == LookupStatus.INVALID.value
    assert r.ip_category == "invalid"


def test_no_databases_loaded():
    svc = GeoIPService(None, None)
    assert svc.lookup("8.8.8.8").lookup_status == LookupStatus.DB_UNAVAILABLE.value
    assert svc.lookup("10.0.0.1").lookup_status == LookupStatus.NOT_PUBLIC.value


def test_missing_db_files_do_not_crash(tmp_path):
    svc = GeoIPService.from_paths(tmp_path / "a.mmdb", tmp_path / "b.mmdb")
    assert not svc.city_available and not svc.asn_available


def test_synthetic_csv_is_explicit_and_skips_private_ips(tmp_path):
    city=tmp_path/"Synthetic-City.csv"
    asn=tmp_path/"Synthetic-ASN.csv"
    city.write_text("ip,country_iso,country,region,city,latitude,longitude,timezone,source\n"
                    "8.8.8.8,US,US,Synthetic region,Synthetic city,,,,synthetic_fixture\n",
                    encoding="utf-8")
    asn.write_text("ip,asn,asn_org,source\n8.8.8.8,4200000001,Synthetic network,synthetic_fixture\n",
                   encoding="utf-8")
    svc=GeoIPService.from_synthetic_csv(city,asn)
    found=svc.lookup("8.8.8.8")
    assert svc.synthetic and found.data_source=="synthetic_fixture"
    assert found.country_iso=="US" and found.asn==4200000001
    assert svc.lookup("10.0.0.1").lookup_status=="not_public"
    svc.close()


def test_cache_avoids_repeat_lookups(service, fake_city_reader):
    for _ in range(5):
        service.lookup("8.8.8.8")
    service.lookup("::ffff:8.8.8.8")  # same address, different spelling
    assert fake_city_reader.calls == 1
    assert service.status()["cache_hits"] == 5


def test_reader_errors_are_contained(fake_asn_reader):
    class BrokenReader:
        def city(self, ip):
            raise RuntimeError("corrupt db")

    r = GeoIPService(BrokenReader(), fake_asn_reader).lookup("8.8.8.8")
    assert r.lookup_status == LookupStatus.PARTIAL.value
    assert r.asn == 15169


def test_lookup_many_dedupes(service, fake_city_reader):
    table = service.lookup_many(["8.8.8.8", "8.8.8.8", "10.0.0.1", None, "bad"])
    assert table.height == 3
    assert fake_city_reader.calls == 1


def test_enrich_ip_columns_keeps_row_count(service):
    frame = pl.DataFrame({"src_ip": ["8.8.8.8", "10.0.0.1", None, "8.8.8.8"],
                          "dst_ip": ["1.1.1.1", "8.8.8.8", "9.9.9.9", None]})
    out = enrich_ip_columns(frame, ["src_ip", "dst_ip", "absent_col"], service)
    assert out.height == 4
    assert out["src_ip_geo_country_iso"].to_list() == ["US", None, None, "US"]
    assert out["src_ip_geo_lookup_status"].to_list() == ["ok", "not_public", None, "ok"]
    assert out["dst_ip_geo_asn"].to_list() == [None, 15169, None, None]


def test_cross_checks():
    frame = pl.DataFrame({"ds_country": ["us", "IN", None, "DE"],
                          "geo_iso": ["US", "DE", "US", None],
                          "ds_asn": ["AS15169", "15169", "1", None],
                          "geo_asn": [15169, 15169, 2, 3]})
    out = cross_check_country(frame, "ds_country", "geo_iso", "c")
    out = cross_check_asn(out, "ds_asn", "geo_asn", "a")
    assert out["c"].to_list() == ["match", "mismatch", "unknown", "unknown"]
    assert out["a"].to_list() == ["match", "match", "mismatch", "unknown"]


def test_haversine():
    assert haversine_km(0, 0, 0, 0) == 0
    # Delhi -> Frankfurt is roughly 6100 km
    assert 5900 < haversine_km(28.61, 77.21, 50.11, 8.68) < 6300
    assert haversine_km(None, 0, 0, 0) is None


def test_real_geolite_if_installed():
    """Integration test: runs only when the real MMDB files are installed."""
    settings = get_settings()
    if not (settings.geolite_city_db.is_file() and settings.geolite_asn_db.is_file()):
        pytest.skip("GeoLite2 databases not installed in data/geolite/")
    svc = GeoIPService.from_paths(settings.geolite_city_db, settings.geolite_asn_db)
    r = svc.lookup("8.8.8.8")
    assert r.lookup_status in {"ok", "partial"}
    assert r.country_iso is not None
    assert svc.lookup("192.168.1.1").lookup_status == "not_public"
    svc.close()
