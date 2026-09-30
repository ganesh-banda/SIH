import json
import polars as pl


def test_health_degraded_without_geolite(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["components"]["duckdb"]["ok"] is True
    assert body["components"]["geolite_city"]["ok"] is False
    assert body["schema_mapping_configured"] is False


def test_geo_endpoint_never_fails(client):
    assert client.get("/geo/ip/192.168.1.1").json()["lookup_status"] == "not_public"
    assert client.get("/geo/ip/not-an-ip").json()["lookup_status"] == "invalid"
    assert client.get("/geo/ip/8.8.8.8").json()["lookup_status"] == "db_unavailable"


def test_dataset_listing_and_inspection(client, test_settings):
    raw = test_settings.raw_dir
    (raw / "sample.json").write_text(json.dumps([{"a": 1, "b": None}, {"a": 2, "b": "x"}]))
    listing = client.get("/datasets").json()
    assert listing == [{"name": "sample.json", "size_bytes": listing[0]["size_bytes"],
                        "format": "json"}]
    body = client.get("/datasets/sample.json/inspect?sample_rows=1").json()
    assert body["rows"] == 2 and body["columns"] == ["a", "b"]
    assert body["null_counts"] == {"a": 0, "b": 1}
    assert len(body["sample"]) == 1


def test_dataset_path_traversal_blocked(client):
    assert client.get("/datasets/..%2F..%2Fetc%2Fpasswd/inspect").status_code == 404
    assert client.get("/datasets/missing.csv/inspect").status_code == 404


def test_canonical_fields(client):
    fields = client.get("/datasets/canonical-fields").json()
    names = {f["name"] for f in fields}
    assert {"txid", "src_ip", "input_addresses"} <= names
    assert all(f["mapped_to"] is None for f in fields)


def test_analysis_endpoints_require_a_run(client):
    for path in ("/transactions", "/transactions/abc", "/wallets", "/wallets/w",
                 "/wallets/w/transactions", "/wallets/w/graph", "/risk/w",
                 "/explanation/w", "/alerts", "/alerts/1"):
        assert client.get(path).status_code == 503, path


def test_analysis_runs_listing(client):
    assert client.get("/analysis/runs").json() == []


def test_alert_sorting_uses_whitelisted_columns(client):
    client.app.state.store.write_table("alerts", pl.DataFrame({
        "alert_id": ["a", "b", "c"],
        "wallet_id": ["wallet-a", "wallet-b", "wallet-c"],
        "risk_score": [90.0, 70.0, 80.0],
        "classification_probability": [0.9, 0.7, 0.8],
        "anomaly_score": [0.1, 0.9, 0.3],
        "graph_risk": [None, None, 0.5],
        "patterns": ["[]", "[]", '[{"pattern":"equal_value_outputs"}]'],
    }))
    assert [item["alert_id"] for item in client.get("/alerts?sort=risk_desc").json()] == ["a", "c", "b"]
    assert [item["alert_id"] for item in client.get("/alerts?sort=risk_asc").json()] == ["b", "c", "a"]
    assert [item["alert_id"] for item in client.get("/alerts?sort=anomaly_desc").json()] == ["b", "c", "a"]
    assert [item["alert_id"] for item in client.get("/alerts?has_pattern=true").json()] == ["c"]
    assert client.get("/alerts?sort=unknown").status_code == 422
