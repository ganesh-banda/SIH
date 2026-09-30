"""Alert creation and ranking.

Ranking is by final risk (descending), ties broken by subject id so the order
is stable and reproducible. Risk levels come from the risk engine and are
UNCALIBRATED until thresholds are set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.risk.risk_engine import RiskAssessment


@dataclass
class Alert:
    alert_id: str
    subject: str
    final_risk: float
    risk_level: str
    signals: dict[str, Any]
    explanation: str | None = None
    top_evidence: list[dict[str, Any]] = field(default_factory=list)
    detected_patterns: list[str] = field(default_factory=list)
    related_transactions: list[str] = field(default_factory=list)
    related_nodes: list[str] = field(default_factory=list)
    rank: int | None = None


def alert_from_assessment(alert_id: str, assessment: RiskAssessment, **extra: Any) -> Alert:
    return Alert(alert_id=alert_id, subject=assessment.subject,
                 final_risk=assessment.final_risk, risk_level=assessment.risk_level.value,
                 signals=assessment.signals.to_dict(), **extra)


def rank_alerts(alerts: list[Alert], min_risk: float | None = None) -> list[Alert]:
    kept = [a for a in alerts if min_risk is None or a.final_risk >= min_risk]
    ranked = sorted(kept, key=lambda a: (-a.final_risk, a.subject))
    for position, alert in enumerate(ranked, start=1):
        alert.rank = position
    return ranked
