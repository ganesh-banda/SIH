"""Train on observation-time features; store full-graph context separately."""
from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from pathlib import Path

import duckdb
import joblib
import networkx as nx
import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, classification_report, confusion_matrix, f1_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from app.config import get_settings
from app.graph.graph_builder import build_graph
from app.ingestion.loader import load_dataset
from app.ingestion.schema_mapping import SchemaMapping
from app.preprocessing.pipeline import preprocess
from app.preprocessing.ip_geolocation import geo_service_for_settings
from app.patterns.transaction_patterns import fit_thresholds, detect_all
from app.risk.risk_engine import RiskSignals, SupervisedOnlyStrategy, risk_level
from app.risk.risk_config import RiskConfig

ROOT = Path(__file__).resolve().parents[2]
SEED = 20240601
FEATURES = ["input_count", "output_count", "total_input", "total_output", "fee",
            "vsize", "fee_rate", "rbf", "version", "locktime_nonzero",
            "max_output_share", "output_amount_cv", "equal_output_fraction",
            "unique_input_count", "unique_output_count"]


def _list(value):
    return value if isinstance(value, (list, tuple, np.ndarray)) else []


def make_features(tx: pd.DataFrame) -> pd.DataFrame:
    """Only features known at observation time; no IDs enter the model."""
    out = tx[["txid"]].copy()
    for col in FEATURES[:9]:
        out[col] = pd.to_numeric(tx[col], errors="coerce")
    out["locktime_nonzero"] = pd.to_numeric(tx.locktime, errors="coerce").ne(0).astype(int)
    amounts = tx.output_amounts.map(_list)
    out["max_output_share"] = amounts.map(lambda a: max(a)/sum(a) if len(a) and sum(a) else 0)
    out["output_amount_cv"] = amounts.map(lambda a: float(np.std(a)/np.mean(a)) if len(a) and np.mean(a) else 0)
    out["equal_output_fraction"] = amounts.map(lambda a: max(pd.Series(a).value_counts())/len(a) if len(a) else 0)
    out["unique_input_count"] = tx.input_addresses.map(lambda a: len(set(_list(a))))
    out["unique_output_count"] = tx.output_addresses.map(lambda a: len(set(_list(a))))
    return out


def metrics(y, p, threshold):
    pred = (p >= threshold).astype(int)
    return {"threshold": float(threshold), "roc_auc": float(roc_auc_score(y, p)),
            "pr_auc": float(average_precision_score(y, p)),
            "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
            "classification_report": classification_report(y, pred, labels=[0, 1],
                target_names=["licit", "illicit"], output_dict=True, zero_division=0)}


def _save(con, name, frame, directory):
    path = directory / f"{name}.parquet"
    frame.to_parquet(path, index=False)
    con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_parquet(?)', [str(path)])


def main() -> None:
    s = get_settings()
    s.ensure_directories()
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    raw = s.raw_dir / "btc_tx_traffic.csv"
    ingested = load_dataset(raw)
    geo = geo_service_for_settings(s)
    try:
        prep = preprocess(ingested, SchemaMapping.from_file(s.schema_mapping_path),
                          geo if (geo.city_available or geo.asn_available) else None)
    finally:
        geo.close()
    normalized = prep.frame
    normalized.write_parquet(s.processed_dir / "normalized_transactions.parquet")
    prep.issues.write_parquet(s.processed_dir / "validation_issues.parquet")
    (reports / "validation.json").write_text(json.dumps(asdict(prep.report), indent=2), encoding="utf-8")
    print("Normalized", normalized.height, "valid", prep.report.valid_records, flush=True)
    tx = normalized.filter(pl.col("_is_valid") & ~pl.col("_is_duplicate")).to_pandas()
    tx["timestamp"] = pd.to_datetime(tx.timestamp, utc=True)
    for col in ("input_count", "output_count", "total_input", "total_output", "fee_rate",
                "vsize", "rbf", "version", "locktime"):
        tx[col] = pd.to_numeric(tx[col], errors="coerce")
    tx = tx.sort_values(["timestamp", "txid"]).reset_index(drop=True)
    labels = pd.read_csv(s.raw_dir / "labels_transactions.csv", usecols=["txid", "label"])
    assert labels.txid.is_unique and tx.txid.is_unique
    tx = tx.merge(labels, on="txid", how="left", validate="one_to_one")
    if tx.label.isna().any():
        raise ValueError("Missing labels for valid transactions")
    y = tx.label.eq("illicit").astype(int).to_numpy()
    n = len(tx)
    tx["split"] = np.where(np.arange(n) < int(.6*n), "train",
                            np.where(np.arange(n) < int(.8*n), "validation", "test"))
    train, val, test = [tx.split.eq(k).to_numpy() for k in ("train", "validation", "test")]
    feats = make_features(tx)
    X = feats[FEATURES].replace([np.inf, -np.inf], np.nan)
    imp = SimpleImputer(strategy="median").fit(X.loc[train])
    Xi = imp.transform(X)
    joblib.dump(imp, s.models_dir / "preprocessing_pipeline.joblib")
    xgb = XGBClassifier(n_estimators=180, max_depth=4, learning_rate=.05,
        subsample=.85, colsample_bytree=.85, objective="binary:logistic",
        eval_metric="logloss", random_state=SEED, n_jobs=4,
        scale_pos_weight=float((1-y[train]).sum()/y[train].sum()))
    xgb.fit(Xi[train], y[train], eval_set=[(Xi[val], y[val])], verbose=False)
    xgb.save_model(s.models_dir / "xgboost_model.json")
    base = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced",
                                                               max_iter=1000, random_state=SEED))
    base.fit(Xi[train], y[train])
    joblib.dump(base, s.models_dir / "logistic_baseline.joblib")
    iso = IsolationForest(n_estimators=150, max_samples=1024, contamination="auto",
                          random_state=SEED, n_jobs=4).fit(Xi[train])
    joblib.dump(iso, s.models_dir / "isolation_forest.joblib")
    p, bp = xgb.predict_proba(Xi)[:,1], base.predict_proba(Xi)[:,1]
    candidates = np.unique(np.quantile(p[val], np.linspace(.01,.99,99)))
    threshold = float(max(candidates, key=lambda t:f1_score(y[val],p[val]>=t,zero_division=0)))
    medium = float(min(np.quantile(p[val],.90), threshold/2))
    raw_anomaly = -iso.score_samples(Xi)
    low,high = np.quantile(raw_anomaly[train],[.01,.99])
    anomaly = np.clip((raw_anomaly-low)/(high-low),0,1)
    evals = {"xgboost":{k:metrics(y[m],p[m],threshold) for k,m in (("validation",val),("test",test))},
             "logistic_baseline":{k:metrics(y[m],bp[m],.5) for k,m in (("validation",val),("test",test))},
             "isolation_forest":{"test_pr_auc_descriptive":float(average_precision_score(y[test],anomaly[test])),
                                 "test_mean_score":float(anomaly[test].mean())}}
    (reports/"model_evaluation.md").write_text("# Held-out evaluation\n\nChronological 60/20/20 split. Threshold selected on validation F1 only. Repeated actors may cross periods; this tests later activity, not unseen actors. Full graph and labels are excluded from model inputs.\n\n```json\n"+json.dumps(evals,indent=2)+"\n```\n",encoding="utf-8")
    pattern_thresholds=fit_thresholds(tx.loc[train])
    fanin=pattern_thresholds["fan_in_gt"]
    patterns=detect_all(tx,pattern_thresholds)
    predictions=pd.DataFrame({"txid":tx.txid,"timestamp":tx.timestamp,"split":tx.split,
        "label":tx.label,"classification_probability":p,"baseline_probability":bp,
        "anomaly_score":anomaly,"anomaly_raw":raw_anomaly,"patterns":patterns})
    print("Models trained; constructing graph",flush=True)
    graph=build_graph(normalized)
    summary=graph.summary()
    structural=nx.Graph()
    for u,v,d in graph.g.edges(data=True):
        if d["edge_type"] in ("input","output"): structural.add_edge(u,v)
    seeds=pd.read_csv(s.raw_dir/"seed_illicit_addresses.csv")
    seed_nodes=["wallet:"+a for a in seeds.address if "wallet:"+a in structural]
    distances=nx.multi_source_dijkstra_path_length(structural,seed_nodes,cutoff=4) if seed_nodes else {}
    print("Graph",summary,"seeds",len(seed_nodes),flush=True)
    wallet_rows=[]
    rel_rows=[]
    for i,row in enumerate(tx.itertuples()):
        for addr in _list(row.input_addresses):
            wallet_rows.append((addr,row.txid,"spend",float(p[i]),float(anomaly[i]),row.timestamp))
            rel_rows.append((addr,row.txid,"input"))
        for addr in _list(row.output_addresses):
            wallet_rows.append((addr,row.txid,"receive",np.nan,np.nan,row.timestamp))
            rel_rows.append((addr,row.txid,"output"))
    wr=pd.DataFrame(wallet_rows,columns=["wallet_id","txid","direction","classification_probability","anomaly_score","timestamp"])
    grp=wr.groupby("wallet_id",sort=False)
    wallets=grp.agg(transaction_count=("txid","nunique"),
        incoming_count=("direction",lambda x:int((x=="receive").sum())),
        outgoing_count=("direction",lambda x:int((x=="spend").sum())),
        classification_probability=("classification_probability","max"),
        anomaly_score=("anomaly_score","max")).reset_index()
    wallets["graph_risk"]=wallets.wallet_id.map(lambda a:1/(distances["wallet:"+a]+1) if "wallet:"+a in distances else np.nan)
    degree=dict(structural.degree())
    component_size={node:len(nodes) for nodes in nx.connected_components(structural) for node in nodes}
    graph_features=pd.DataFrame({"wallet_id":wallets.wallet_id,
        "structural_degree":wallets.wallet_id.map(lambda a:degree.get("wallet:"+a,0)),
        "component_size":wallets.wallet_id.map(lambda a:component_size.get("wallet:"+a,1)),
        "seed_distance_le4":wallets.wallet_id.map(lambda a:distances.get("wallet:"+a))})
    # Common-input association is only a candidate. Equal-output transactions
    # and unusually large input sets are excluded to reduce CoinJoin joins.
    parent={}
    evidence=[]
    def find(a):
        parent.setdefault(a,a)
        while parent[a]!=a:
            parent[a]=parent[parent[a]]
            a=parent[a]
        return a
    for row in tx.itertuples():
        ins=list(dict.fromkeys(_list(row.input_addresses)))
        outs=_list(row.output_amounts)
        if not 2<=len(ins)<=fanin or (len(outs)>2 and len(set(outs))==1): continue
        for a in ins[1:]:
            ra,rb=find(ins[0]),find(a)
            if ra!=rb: parent[rb]=ra
            evidence.append((ins[0],a,row.txid,"common_input_candidate"))
    groups={a:find(a) for a in parent}
    entity_candidates=pd.DataFrame({"wallet_id":list(groups),
        "possible_entity_group":["possible_"+hashlib.sha256(v.encode()).hexdigest()[:16] for v in groups.values()],
        "method":"common_input_candidate"})
    strategy=SupervisedOnlyStrategy()
    category_config=RiskConfig(threshold_medium=100*medium,threshold_high=100*threshold)
    wallets["risk_score"]=wallets.classification_probability.map(
        lambda x: strategy.fuse(RiskSignals(classification_probability=float(x))) if pd.notna(x) else np.nan)
    wallets["risk_category"]=wallets.risk_score.map(
        lambda x:risk_level(float(x),category_config).value if pd.notna(x) else "UNSCORED")
    import shap
    flagged=np.flatnonzero(p>=threshold)
    selected=flagged
    sv=shap.TreeExplainer(xgb).shap_values(Xi[selected]) if len(selected) else np.empty((0,len(FEATURES)))
    shap_rows=[]
    for i,values in zip(selected,sv):
        top=np.argsort(np.abs(values))[-5:][::-1]
        shap_rows.append({"txid":tx.txid.iloc[i],"model_evidence":json.dumps([
            {"feature":FEATURES[j],"value":float(Xi[i,j]),"shap_log_odds":float(values[j])} for j in top])})
    predictions=predictions.merge(pd.DataFrame(shap_rows,columns=["txid","model_evidence"]),on="txid",how="left")
    pred_lookup=predictions.set_index("txid")
    alerts=[]
    spend_groups={a:g.sort_values("classification_probability",ascending=False)
                  for a,g in wr[wr.direction.eq("spend")].groupby("wallet_id",sort=False)}
    for _,w in wallets[wallets.risk_category.eq("HIGH")].sort_values("risk_score",ascending=False).iterrows():
        spends=spend_groups.get(w.wallet_id)
        if spends is None: continue
        best=pred_lookup.loc[spends.txid.iloc[0]]
        explanation=f"Address spent in {int(w.outgoing_count)} observed transaction(s). Highest transaction model probability: {float(w.classification_probability):.3f}."
        graph_evidence=[]
        if pd.notna(w.graph_risk):
            hops=int(round(1/float(w.graph_risk)-1))
            graph_evidence=[{"type":"seed_distance","structural_edges":hops,"score":float(w.graph_risk)}]
            explanation+=f" A known seed is {hops} structural edge(s) away; proximity is contextual."
        model_evidence=json.loads(best.model_evidence) if isinstance(best.model_evidence,str) else []
        if model_evidence:
            top=model_evidence[0]
            explanation+=f" For the highest-scored transaction, {top['feature']} contributed {top['shap_log_odds']:+.3f} to model log-odds."
        for pattern in json.loads(best.patterns):
            if pattern["pattern"]=="unusual_fan_out":
                explanation+=f" That transaction had {pattern['output_count']} outputs, above the training 99th percentile of {pattern['training_p99']}."
            elif pattern["pattern"]=="unusual_fan_in":
                explanation+=f" It had {pattern['input_count']} inputs, above the training 99th percentile of {pattern['training_p99']}."
            elif pattern["pattern"]=="equal_value_outputs":
                explanation+=f" It had {pattern['output_count']} outputs of {pattern['amount_sats']} satoshis each."
        alerts.append({"alert_id":f"alert_{len(alerts)+1:05d}","wallet_id":w.wallet_id,
            "risk_score":float(w.risk_score),"risk_category":w.risk_category,
            "classification_probability":float(w.classification_probability),
            "anomaly_score":float(w.anomaly_score),"graph_risk":float(w.graph_risk) if pd.notna(w.graph_risk) else None,
            "patterns":best.patterns,"graph_evidence":json.dumps(graph_evidence),
            "model_evidence":best.model_evidence if isinstance(best.model_evidence,str) else "[]",
            "explanation":explanation,"related_transactions":json.dumps(spends.txid.head(20).tolist())})
    con=duckdb.connect(str(s.duckdb_path))
    _save(con,"transactions",tx.drop(columns=["label"]),s.processed_dir)
    _save(con,"ml_features",feats,s.features_dir)
    _save(con,"predictions",predictions,s.results_dir)
    _save(con,"wallet_transactions",wr,s.results_dir)
    _save(con,"wallets",wallets,s.results_dir)
    _save(con,"graph_edges",pd.DataFrame(rel_rows,columns=["wallet_id","txid","edge_type"]),s.results_dir)
    _save(con,"graph_features",graph_features,s.features_dir)
    _save(con,"entity_candidates",entity_candidates,s.results_dir)
    _save(con,"entity_association_evidence",pd.DataFrame(evidence,columns=["wallet_a","wallet_b","txid","method"]),s.results_dir)
    _save(con,"alerts",pd.DataFrame(alerts),s.results_dir)
    con.close()
    config={"seed":SEED,"features":FEATURES,"split":"chronological_60_20_20",
        "train_rows":int(train.sum()),"validation_rows":int(val.sum()),"test_rows":int(test.sum()),
        "high_probability_threshold":threshold,"medium_probability_threshold":medium,
        "risk_method":"100 * maximum XGBoost probability of transactions spent by address",
        "anomaly_normalization":{"training_p01":float(low),"training_p99":float(high)},
        "pattern_thresholds":pattern_thresholds,
        "graph_summary":summary,"seed_nodes_present":len(seed_nodes),
        "source_sha256":ingested.sha256,
        "geolite_status":"synthetic_fixture" if geo.synthetic else
            ("geolite_mmdb" if (geo.city_available or geo.asn_available) else "GeoLite database required")}
    (s.models_dir/"feature_schema.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    (reports/"training_summary.md").write_text("# Training summary\n\n```json\n"+json.dumps(config,indent=2)+"\n```\n\nRisk is based on supervised transaction probability only. Anomaly, seed proximity and patterns stay independent evidence. This is not a calibrated wallet-criminality probability.\n",encoding="utf-8")
    print("Completed",len(predictions),"predictions",len(wallets),"wallets",len(alerts),"alerts",flush=True)


if __name__=="__main__": main()
