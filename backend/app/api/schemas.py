"""API response/request models (kept separate from ML/domain code)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    components: dict[str, ComponentStatus]
    schema_mapping_configured: bool


class GeoLookupResponse(BaseModel):
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


class DatasetFile(BaseModel):
    name: str
    size_bytes: int
    format: str | None


class DatasetInspection(BaseModel):
    source: str
    format: str
    sha256: str
    rows: int
    columns: list[str]
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    sample: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalFieldInfo(BaseModel):
    name: str
    kind: str
    description: str
    source: str
    mapped_to: str | None = None


class PendingResponse(BaseModel):
    detail: str


class DatasetSummaryResponse(BaseModel):
    transactions: int
    wallets: int
    alerts: int


class RiskResponse(BaseModel):
    wallet_id: str
    risk_score: float | None
    risk_category: str
    classification_probability: float | None
    anomaly_score: float | None
    graph_risk: float | None


class GraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
