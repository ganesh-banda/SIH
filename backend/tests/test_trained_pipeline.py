from pathlib import Path

import pandas as pd
import pytest

from app.models.train import FEATURES, make_features
from app.models.model_loader import load_trained_bundle
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


def test_supervised_risk_keeps_other_signals_separate():
    engine=RiskEngine(RiskConfig(threshold_medium=30,threshold_high=70),SupervisedOnlyStrategy())
    result=engine.assess("a",RiskSignals(classification_probability=.8,anomaly_score=.1,graph_risk=.9))
    assert result.final_risk==80
    assert result.risk_level.value=="HIGH"
    assert result.signals.graph_risk==.9
