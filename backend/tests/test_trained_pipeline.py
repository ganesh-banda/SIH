from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.models.train import FEATURES, make_features
from app.models.anomaly_model import anomaly_scores, train_isolation_forest
from app.models.base import ModelMetadata
from app.models.evaluate import evaluate
from app.models.model_loader import list_model_metadata, load_trained_bundle
from app.models.xgboost_model import predict_proba, train_xgboost
from app.patterns.transaction_patterns import detect_transaction
from app.risk.risk_engine import RiskEngine, RiskSignals, SupervisedOnlyStrategy
from app.risk.risk_config import RiskConfig


def test_observation_features_and_patterns():
    tx=pd.DataFrame([{"txid":"t","input_count":1,"output_count":3,"total_input":101,
        "total_output":100,"fee":1,"vsize":100,"fee_rate":.01,"rbf":0,
        "version":2,"locktime":0,"input_addresses":["a"],
        "output_addresses":["b","c","d"],"output_amounts":[20,40,40]}])
    f=make_features(tx)
    assert f.loc[0,"max_output_share"]==.4
    assert f.loc[0,"equal_output_fraction"]==2/3
    assert f.loc[0,"unique_output_count"]==3
    assert set(f.columns)=={"txid",*FEATURES}
    evidence=detect_transaction(next(tx.itertuples()),{"fan_out_gt":2,"fan_in_gt":5})
    assert evidence==[{"pattern":"unusual_fan_out","output_count":3,"training_p99":2}]


def test_saved_models_load_if_analysis_has_run():
    directory=Path(__file__).resolve().parents[1]/"models"
    if not (directory/"feature_schema.json").exists():
        pytest.skip("Training has not been run in this workspace")
    bundle=load_trained_bundle(directory)
    assert bundle["schema"]["features"]==FEATURES
    assert bundle["classifier"].n_features_in_==len(FEATURES)
    backend=directory.parent
    features=pd.read_parquet(backend/"data/features/ml_features.parquet").head(12)
    predictions=pd.read_parquet(backend/"data/results/predictions.parquet")
    saved=predictions.set_index("txid").loc[features.txid]
    transformed=bundle["imputer"].transform(features[FEATURES])
    np.testing.assert_allclose(predict_proba(bundle["classifier"],transformed),
                               saved.classification_probability,rtol=1e-6)
    np.testing.assert_allclose(bundle["baseline"].predict_proba(transformed)[:,1],
                               saved.baseline_probability,rtol=1e-6)
    np.testing.assert_allclose(anomaly_scores(bundle["isolation_forest"],transformed),
                               saved.anomaly_raw,rtol=1e-6)


def test_model_helpers_fit_score_and_evaluate(tmp_path):
    rng=np.random.default_rng(42)
    labels=np.array([0,1]*40)
    features=rng.normal(size=(80,4))+labels[:,None]*.6
    classifier=train_xgboost(features[:60],labels[:60],features[60:],labels[60:])
    probabilities=predict_proba(classifier,features[60:])
    assert probabilities.shape==(20,)
    assert np.all((probabilities>=0)&(probabilities<=1))
    report=evaluate(labels[60:],probabilities,.5)
    assert len(report["confusion_matrix"])==2
    assert 0<=report["pr_auc"]<=1
    anomaly=train_isolation_forest(features[:60])
    assert np.isfinite(anomaly_scores(anomaly,features[60:])).all()
    with pytest.raises(ValueError,match="features do not match"):
        predict_proba(classifier,features[60:,:2])
    with pytest.raises(ValueError,match="features do not match"):
        anomaly_scores(anomaly,features[60:,:2])
    with pytest.raises(ValueError,match="both binary classes"):
        train_xgboost(features[:4],np.zeros(4))
    with pytest.raises(ValueError,match="both binary classes"):
        evaluate(np.zeros(4),np.zeros(4),.5)
    with pytest.raises(FileNotFoundError,match="Missing trained model artifacts"):
        load_trained_bundle(tmp_path)


def test_optional_model_metadata_round_trip(tmp_path):
    metadata=ModelMetadata(
        name="tiny",model_type="xgboost",version="1",trained_at="2024-06-01T00:00:00Z",
        feature_names=["a","b"],dataset_sha256="abc",training_config={"seed":42},
    )
    path=tmp_path/"tiny.meta.json"
    metadata.save(path)
    assert ModelMetadata.load(path)==metadata
    (tmp_path/"broken.meta.json").write_text("{invalid",encoding="utf-8")
    assert list_model_metadata(tmp_path)==[metadata]


def test_supervised_risk_keeps_other_signals_separate():
    engine=RiskEngine(RiskConfig(threshold_medium=30,threshold_high=70),SupervisedOnlyStrategy())
    result=engine.assess("a",RiskSignals(classification_probability=.8,anomaly_score=.1,graph_risk=.9))
    assert result.final_risk==80
    assert result.risk_level.value=="HIGH"
    assert result.signals.graph_risk==.9
