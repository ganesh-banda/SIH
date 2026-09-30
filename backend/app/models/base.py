"""Model metadata, persisted next to every trained model.

Every model saved to ``models/`` gets a ``<name>.meta.json`` recording what
it was trained on and how, so any score can be traced to an exact model,
feature list and dataset hash.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelMetadata:
    name: str
    model_type: str                    # "xgboost" | "isolation_forest" | ...
    version: str
    trained_at: str                    # ISO-8601 UTC
    feature_names: list[str]
    dataset_sha256: str | None = None
    split_strategy: str | None = None  # temporal / group-aware / component-aware
    training_config: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    label_definition: str | None = None

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ModelMetadata":
        return cls(**json.loads(path.read_text(encoding="utf-8")))
