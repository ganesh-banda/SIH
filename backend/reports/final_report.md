# Final implementation report

## Dataset and target

The attached archive is `synthetic_btc_dataset.zip`. The main traffic file contains **20,844 rows × 30 columns**. All 20,844 records validated; duplicate rows, duplicate TXIDs, invalid IPs, nonpublic IPs and missing critical fields were zero. Observation time spans 2024-06-01 00:00:28.340 UTC to 2024-06-02 15:55:02.659 UTC. See [dataset_audit.md](dataset_audit.md) for every column, type, missing count, cardinality, examples, invalid-value checks and amount distributions.

The target is binary `labels_transactions.label`: **19,524 licit and 1,320 illicit** transactions (6.33% illicit). This label is defined by the spender of transaction inputs. The separate address/entity label files are ground truth only; 40 known seed addresses are supplied. The traffic's `asn` and `as_org` are entirely empty. The original raw CSVs and generator metadata remain unmodified in `data/raw/`.

## Implementation

- Normalization validates timestamps, TXIDs, ports, IPs, addresses and delimited address/amount lists, retaining record indices and issue tables. All 20,844 records are valid.
- The 15 model features are listed with source columns and calculations in [feature_dictionary.md](feature_dictionary.md). They use only the current transaction. Model inputs exclude labels, typology, IDs, seeds, geography and graph state.
- Graph schema: address → transaction for spending inputs; transaction → address for outputs; observed source/destination IP → transaction for network observations. It contains **64,414 address nodes, 20,844 transaction nodes, 604 IP nodes, zero entity nodes, and 146,242 edges**.
- Candidate entity associations use common input addresses except equal-output transactions and input sets larger than the training 99th percentile. They are *possible associations*, not ownership attribution: 21,658 addresses appear in 6,224 candidate groups. Ground-truth entity IDs are not used.
- Graph context stores structural degree, component size and distance to supplied seed addresses. IP edges are excluded from proximity. Of 40 supplied seeds, 29 appear in the observed graph; 768 addresses are within four structural edges. Graph risk is `1/(distance+1)` where reached, otherwise null. It does not alter the model score.
- Implemented structural patterns: unusual fan-out (210 transactions), unusual fan-in (132), and equal-value outputs (25). Fan thresholds use the training 99th percentiles: output count greater than 27, input count greater than 10. These are observations, not crime findings. Peeling, rapid forwarding, cycles, mixing, IP switching, ASN switching, geographic distance and city-level features are not claimed or implemented; the required inputs or robust validation are not available in this version.
- Real GeoLite MMDBs are absent: **GeoLite database required** for real enrichment. Explicitly labelled [synthetic City/ASN CSV fixtures](synthetic_geo.md) now enrich all 20,844 transactions for local testing. No download or remote lookup occurred. Country and ASN remain contextual and are excluded from risk features.

## Training and held-out evaluation

Observation-time chronological split: 12,506 training, 4,169 validation, 4,169 test transactions. The imputer fits on train only; the positive threshold maximizes F1 on validation only. Row-local features avoid future graph information. Repeated actors can appear across periods, so this evaluates later transactions from a partly familiar population, not unseen actors. No wallet identifier enters a classifier.

| Test model | PR-AUC | ROC-AUC | Illicit precision | Illicit recall | Illicit F1 | Confusion matrix (licit/illicit) |
|---|---:|---:|---:|---:|---:|---|
| XGBoost | 0.377 | 0.934 | 0.402 | 0.500 | 0.446 | [[3897,116],[78,78]] |
| Logistic Regression baseline | 0.180 | 0.898 | 0.149 | 0.821 | 0.252 | [[3282,731],[28,128]] |

The Isolation Forest is secondary and unsupervised. Negative `score_samples` values are linearly mapped to [0,1] using train-set 1st/99th percentiles 0.35128 and 0.66467, then clipped. Its test PR-AUC against labels is **0.0323**, below the test positive prevalence; this signal should not be treated as a probability or a reliable stand-alone detector. Full metrics and validation results are in [model_evaluation.md](model_evaluation.md).

## Scoring and evidence

For an address that spends inputs, the displayed score is **100 × the maximum XGBoost transaction probability across its observed spending transactions**. It is not a calibrated probability that the address owner is criminal. HIGH begins at 0.678199768 transaction probability, selected by validation F1. MEDIUM begins at 0.339099884, the smaller of the validation 90th percentile and half the HIGH threshold. Scores from Isolation Forest, seed proximity and patterns remain separate. Result counts: 1,877 HIGH alerts, 1,349 MEDIUM addresses, 33,691 LOW, and 27,497 addresses without an observed spend and therefore unscored.

SHAP uses tree log-odds contributions, not percentage points. For the highest-scored alert's spending transaction, `total_input=959750666` satoshis contributes **+1.794** model log-odds, and `max_output_share=1.0` contributes **+1.202**. One generated alert:

```json
{
  "alert_id": "alert_00001",
  "wallet_id": "bc1qfjhxltuem89de6pwfgjrw2ftc6v3zy5ryufvwq",
  "risk_score": 99.58658218383789,
  "risk_category": "HIGH",
  "classification_probability": 0.9958658218383789,
  "anomaly_score": 0.5377943372330696,
  "graph_risk": null,
  "related_transaction": "d8dfe2b665d4a0015d19b26064c8eb717c24f98e1167b460db44208ceb45e28b",
  "explanation": "Address spent in 1 observed transaction(s). Highest transaction model probability: 0.996. For the highest-scored transaction, total_input contributed +1.794 to model log-odds."
}
```

The stored alert also carries structured model, graph and pattern evidence. No LLM generates core explanations.

## Artifacts and verification

The project tree, omitting virtual environments and package internals:

```
backend/
  app/
    api/                 routes, response schemas, persisted-result query helper
    ingestion/           original format loaders and mapped schema
    preprocessing/       original normalization, validation and local GeoIP
    graph/               original NetworkX builder and query interfaces
    features/            feature interfaces
    models/              executable train pipeline and model loader
    patterns/            transaction pattern detector and original interfaces
    risk/, explainability/, alerts/, storage/
  config/schema_mapping.json
  scripts/import_archive.py, audit_official.py, smoke_api.py, report_stats.py, plot_confusion.py, create_synthetic_geo.py
  data/raw/              copied original archive members
  data/geolite/          clearly marked synthetic City/ASN CSV fixtures
  data/processed/        normalized records, validation issues, transaction Parquet
  data/features/         model and graph feature Parquet
  data/results/          DuckDB, predictions, graph edges, candidates, alerts
  models/                XGBoost JSON, imputer, baseline, Isolation Forest, feature schema
  reports/               audit, feature dictionary, evaluation, training summary, this report
  tests/                 phase-one tests and trained-pipeline tests
  README.md, requirements.txt, requirements-ml.txt
```

New or changed source: `config/schema_mapping.json`, `app/models/train.py`, `app/models/model_loader.py`, `app/patterns/transaction_patterns.py`, `app/risk/risk_engine.py`, `app/api/query.py`, `app/api/schemas.py`, `app/api/routes/{datasets,transactions,wallets,alerts,analysis}.py`, `app/main.py`, `app/preprocessing/ip_geolocation.py`, `app/preprocessing/geo_features.py`, `app/config.py`, `scripts/{import_archive,audit_official,smoke_api,report_stats,plot_confusion,create_synthetic_geo}.py`, `tests/{test_api,test_trained_pipeline,test_geolocation}.py`, `.env.example`, and `README.md`. The trained files listed above were created by actually running the pipeline. Confusion plots are in `reports/plots/`.

The pytest suite passed with one existing conditional GeoLite test skipped. The API smoke run passed the requested data routes, and `POST /analysis/run` was executed successfully.

## Commands

From `backend/` on Windows:

```powershell
.\env\Scripts\python.exe -m pip install -r requirements-ml.txt
.\env\Scripts\python.exe -m scripts.import_archive "C:\Users\Owner\Downloads\synthetic_btc_dataset.zip"
.\env\Scripts\python.exe -m scripts.audit_official
.\env\Scripts\python.exe -m scripts.create_synthetic_geo
.\env\Scripts\python.exe -m app.models.train
.\env\Scripts\python.exe -m scripts.plot_confusion
.\env\Scripts\python.exe -m scripts.smoke_api
.\env\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.\env\Scripts\python.exe -m pytest -q
```

For GeoLite, place `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb` under `data/geolite/`, then rerun analysis. The prototype assumes satoshi units per the archive README and uses observation timestamp for chronological ordering. It does not assume an IP is controlled by any input or output address.
