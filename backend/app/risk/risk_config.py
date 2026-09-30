"""Risk configuration.

Everything defaults to "not decided". There are no default weights and no
default LOW/MEDIUM/HIGH thresholds: both are set only after calibration on
the real dataset.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    threshold_medium: float | None = None  # 0-100 scale, set after calibration
    threshold_high: float | None = None

    def __post_init__(self) -> None:
        m, h = self.threshold_medium, self.threshold_high
        if (m is None) != (h is None):
            raise ValueError("Set both risk thresholds or neither")
        if m is not None and not (0 <= m < h <= 100):
            raise ValueError("Thresholds must satisfy 0 <= medium < high <= 100")

    @property
    def calibrated(self) -> bool:
        return self.threshold_medium is not None
