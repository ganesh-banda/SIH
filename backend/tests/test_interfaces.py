"""Tests for the dataset-independent parts of features/risk/explain/alerts."""

import polars as pl
import pytest

from app.alerts.alert_engine import Alert, alert_from_assessment, rank_alerts
from app.explainability.evidence_builder import EvidenceBundle, EvidenceItem, EvidenceKind
from app.explainability.explanation_generator import generate_explanation
from app.explainability.pattern_evidence import pattern_to_evidence
from app.explainability.templates import fmt_count, fmt_duration, fmt_percent
from app.features.feature_pipeline import IdentifierLeakError, assert_no_identifier_columns
from app.patterns.base import PatternResult
from app.patterns.pattern_engine import run_patterns
from app.patterns.peeling_chain import Detector as PeelingDetector
from app.risk.risk_config import RiskConfig
from app.risk.risk_engine import (
    RiskEngine, RiskEngineNotConfigured, RiskLevel, RiskSignals, risk_level,
)


# --- features ---------------------------------------------------------------

def test_identifier_guard():
    assert_no_identifier_columns(pl.DataFrame({"wallet_id": ["a"], "f1": [1]}), key="wallet_id")
    with pytest.raises(IdentifierLeakError):
        assert_no_identifier_columns(pl.DataFrame({"wallet_id": ["a"], "txid": ["t"]}),
                                     key="wallet_id")


# --- explanation templates / generator -----------------------------------------

def test_formatters():
    assert fmt_percent(0.934) == "93%"
    assert fmt_duration(120) == "2 minutes"
    assert fmt_duration(60) == "1 minute"
    assert fmt_duration(45) == "45 seconds"
    assert fmt_duration(5400) == "1.5 hours"
    assert fmt_count(1, "wallet") == "1 wallet"
    assert fmt_count(21, "destination wallet") == "21 destination wallets"


def _test_templates():
    def fan_out(v):
        if "destination_count" not in v:
            return None
        return f"Funds were distributed across {fmt_count(v['destination_count'], 'destination wallet')}."
    return {"high_fan_out": fan_out}


def test_explanation_only_uses_existing_evidence():
    bundle = EvidenceBundle(subject="Wallet X", final_risk=87.2)
    bundle.add(EvidenceItem(EvidenceKind.PATTERN, "high_fan_out", {"destination_count": 21}))
    bundle.add(EvidenceItem(EvidenceKind.PATTERN, "high_fan_out", {}))           # incomplete
    bundle.add(EvidenceItem(EvidenceKind.GRAPH, "unregistered_type", {"x": 1}))  # no template
    exp = generate_explanation(bundle, _test_templates())
    assert exp.summary == "Wallet X received a risk score of 87/100."
    assert [s["text"] for s in exp.sentences] == [
        "Funds were distributed across 21 destination wallets."]
    assert exp.sentences[0]["evidence_index"] == 0
    assert {u["reason"] for u in exp.unexplained} == {"missing values", "no template"}
    assert "unregistered" not in exp.text


def test_explanation_without_score_has_no_summary():
    exp = generate_explanation(EvidenceBundle(subject="w"), {})
    assert exp.summary is None and exp.text == ""


def test_pattern_to_evidence():
    assert pattern_to_evidence(PatternResult("p", "wallet:a", detected=False)) is None
    item = pattern_to_evidence(PatternResult("p", "wallet:a", True, 0.8, {"chain_length": 7}))
    assert item.values == {"chain_length": 7, "score": 0.8}


# --- patterns ---------------------------------------------------------------

def test_pattern_engine_isolates_failures():
    class Good:
        name = "good"
        def detect(self, graph):
            return [PatternResult("good", "wallet:a", True)]

    class Broken:
        name = "broken"
        def detect(self, graph):
            raise RuntimeError("boom")

    run = run_patterns(graph=None, detectors=[Good(), Broken(), PeelingDetector()])
    assert len(run.results) == 1
    assert run.failed_detectors == {"broken": "RuntimeError", "peeling_chain": "not implemented"}


# --- risk -------------------------------------------------------------------

def test_uncalibrated_by_default():
    assert risk_level(99, RiskConfig()) is RiskLevel.UNCALIBRATED


def test_levels_when_calibrated():
    cfg = RiskConfig(threshold_medium=50, threshold_high=80)
    assert [risk_level(s, cfg) for s in (10, 50, 80)] == [
        RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]


@pytest.mark.parametrize("m, h", [(80, 50), (50, None), (-1, 50), (50, 101)])
def test_invalid_thresholds(m, h):
    with pytest.raises(ValueError):
        RiskConfig(threshold_medium=m, threshold_high=h)


def test_engine_requires_strategy():
    with pytest.raises(RiskEngineNotConfigured):
        RiskEngine(RiskConfig()).assess("w", RiskSignals())


def test_engine_with_injected_strategy_and_range_check():
    class Const:
        name = "test_const"
        def __init__(self, v):
            self.v = v
        def fuse(self, signals):
            return self.v

    a = RiskEngine(RiskConfig(), Const(42)).assess("w", RiskSignals(anomaly_score=-0.3))
    assert a.final_risk == 42 and a.risk_level is RiskLevel.UNCALIBRATED
    assert a.signals.anomaly_score == -0.3  # signals preserved separately
    with pytest.raises(ValueError):
        RiskEngine(RiskConfig(), Const(150)).assess("w", RiskSignals())


# --- alerts -----------------------------------------------------------------

def test_rank_alerts_stable_order():
    alerts = [Alert("1", "b", 50, "LOW", {}), Alert("2", "a", 50, "LOW", {}),
              Alert("3", "c", 90, "HIGH", {}), Alert("4", "d", 10, "LOW", {})]
    ranked = rank_alerts(alerts, min_risk=20)
    assert [a.subject for a in ranked] == ["c", "a", "b"]
    assert [a.rank for a in ranked] == [1, 2, 3]


def test_alert_from_assessment():
    class Const:
        name = "c"
        def fuse(self, s):
            return 70
    a = RiskEngine(RiskConfig(50, 80), Const()).assess("w", RiskSignals(graph_risk=0.5))
    alert = alert_from_assessment("al1", a)
    assert alert.risk_level == "MEDIUM" and alert.signals["graph_risk"] == 0.5
