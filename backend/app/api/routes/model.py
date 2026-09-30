"""Read persisted evaluation metadata for the dashboard."""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_app_settings
from app.config import Settings

router=APIRouter(prefix="/model",tags=["model"])


@router.get("/summary")
def model_summary(settings:Settings=Depends(get_app_settings)):
    config_path=settings.models_dir/"feature_schema.json"
    evaluation_path=settings.models_dir.parent/"reports/model_evaluation.md"
    if not config_path.is_file() or not evaluation_path.is_file():
        raise HTTPException(503,"Model evaluation has not been generated")
    config=json.loads(config_path.read_text(encoding="utf-8"))
    evaluation_text=evaluation_path.read_text(encoding="utf-8")
    evaluation=json.loads(evaluation_text.split("```json",1)[1].split("```",1)[0])
    test=evaluation["xgboost"]["test"]
    positive=test["classification_report"]["illicit"]
    baseline=evaluation["logistic_baseline"]["test"]
    return {"split":config["split"],"features":config["features"],
            "positive_label":"illicit","risk_method":config["risk_method"],
            "threshold":config["high_probability_threshold"],
            "test":{"pr_auc":test["pr_auc"],"roc_auc":test["roc_auc"],
                    "precision":positive["precision"],"recall":positive["recall"],
                    "f1":positive["f1-score"],"support":positive["support"]},
            "baseline_test_pr_auc":baseline["pr_auc"],
            "anomaly_test_pr_auc":evaluation["isolation_forest"]["test_pr_auc_descriptive"]}
