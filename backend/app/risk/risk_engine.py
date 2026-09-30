"""Risk engine: combines separate detection signals into one 0-100 score.

The signals stay separate (``RiskSignals``) and are always returned alongside
the final score. HOW they are combined is a pluggable ``FusionStrategy``;
none is provided yet on purpose (no arbitrary weights).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Protocol

from app.risk.risk_config import RiskConfig


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNCALIBRATED = "UNCALIBRATED"  # thresholds not set yet


@dataclass
class RiskSignals:
    """Independent signals for one subject. Any may be missing."""

    classification_probability: float | None = None  # XGBoost
    anomaly_score: float | None = None               # Isolation Forest (raw)
    graph_risk: float | None = None                  # propagation
    pattern_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class FusionStrategy(Protocol):
    name: str

    def fuse(self, signals: RiskSignals) -> float:
        """Return a score in [0, 100]."""
        ...


class SupervisedOnlyStrategy:
    """No arbitrary fusion weights: probability alone sets the displayed score."""
    name = "supervised_transaction_probability"

    def fuse(self, signals: RiskSignals) -> float:
        if signals.classification_probability is None:
            raise ValueError("No supervised probability; subject is unscored")
        return 100.0 * signals.classification_probability


@dataclass
class RiskAssessment:
    subject: str
    final_risk: float
    risk_level: RiskLevel
    fusion_method: str
    signals: RiskSignals


class RiskEngineNotConfigured(RuntimeError):
    pass


def risk_level(score: float, config: RiskConfig) -> RiskLevel:
    if not config.calibrated:
        return RiskLevel.UNCALIBRATED
    assert config.threshold_medium is not None and config.threshold_high is not None
    if score >= config.threshold_high:
        return RiskLevel.HIGH
    if score >= config.threshold_medium:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


class RiskEngine:
    def __init__(self, config: RiskConfig, strategy: FusionStrategy | None = None) -> None:
        self.config = config
        self.strategy = strategy

    def assess(self, subject: str, signals: RiskSignals) -> RiskAssessment:
        if self.strategy is None:
            raise RiskEngineNotConfigured(
                "No fusion strategy configured; it is chosen after calibration on real data."
            )
        score = float(self.strategy.fuse(signals))
        if not 0.0 <= score <= 100.0:
            raise ValueError(f"Fusion strategy '{self.strategy.name}' returned {score}, "
                             "outside [0, 100]")
        return RiskAssessment(subject, score, risk_level(score, self.config),
                              self.strategy.name, signals)
