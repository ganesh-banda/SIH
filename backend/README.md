# Synthetic Bitcoin risk analysis backend

Offline FastAPI, DuckDB, Parquet, NetworkX and ML pipeline built around the supplied synthetic Bitcoin archive. The source CSVs remain in `data/raw/`. This is an investigation aid; address scores are derived from transactions spent by that address and are not proof of ownership or wrongdoing.

## Set up and run

From this `backend` directory, using Python 3.11 or newer:

```powershell
python -m venv env
.\env\Scripts\python.exe -m pip install -r requirements-ml.txt
.\env\Scripts\python.exe -m scripts.import_archive "C:\Users\Owner\Downloads\synthetic_btc_dataset.zip"
.\env\Scripts\python.exe -m scripts.audit_official
.\env\Scripts\python.exe -m app.models.train
.\env\Scripts\python.exe -m scripts.plot_confusion
.\env\Scripts\python.exe -m pytest -q
.\env\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Linux, use `python3 -m venv .venv`, `./.venv/bin/python`, and the appropriate archive path. Dependencies are installed once; inference and API access then work offline. The API does not train on startup. `POST /analysis/run` explicitly repeats the pipeline.

For real city and ASN enrichment, put licensed local `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb` in `data/geolite/`, or set `BTCRISK_GEOLITE_CITY_DB` and `BTCRISK_GEOLITE_ASN_DB`. **GeoLite database required** for real enrichment. Local [synthetic CSV fixtures](reports/synthetic_geo.md) are enabled in this workspace through `.env`; regenerate with `python -m scripts.create_synthetic_geo`. They are test data, and the API labels them `synthetic_fixture`. Installed MMDBs take precedence. Country never raises risk by itself.

## Method

- The attached label file supplies a binary transaction target: the spender of inputs is licit or illicit. Labels, entity IDs, typology names, seed membership and network identifiers are excluded from features.
- Transactions are ordered by observation time: first 60% train, next 20% validation, final 20% test. Only row-local fields enter the models. Repeated entities can occur in multiple periods, so this is a future-activity test rather than unseen-entity generalization.
- XGBoost is the supervised detector; Logistic Regression is a baseline. Isolation Forest is independent. Its displayed score is a clipped linear transform of the negative raw score using training 1st and 99th percentiles, not a probability.
- The address risk score is 100 times the highest XGBoost probability among transactions it spends. The HIGH threshold maximizes positive F1 on validation; MEDIUM is the smaller of the validation 90th probability percentile and half the HIGH threshold. These thresholds are prioritization choices, not a calibrated criminality probability.
- Full-graph seed distance, association candidates and patterns are post-hoc context. IP edges are excluded from seed-distance propagation. A shared peer does not associate wallets. Common-input candidates exclude large input sets and equal-output transactions but can still merge unrelated actors.
- SHAP contributions are in model log-odds units. Alerts include deterministic text tied to actual counts, probabilities and seed distance. No LLM or remote inference is used.

## Results and storage

See [dataset audit](reports/dataset_audit.md), [feature dictionary](reports/feature_dictionary.md), [evaluation](reports/model_evaluation.md), and [training summary](reports/training_summary.md). The raw archive is never modified. Normalized records and validation issues are in `data/processed/`; features in `data/features/`; predictions, graph/association tables, wallet results and alerts in `data/results/`; model artifacts in `models/`. DuckDB stores the same queryable tables at `data/results/analysis.duckdb`.

The current run completed 20,844 transactions, 64,414 addresses, 604 IP nodes, and 146,242 graph edges. Local GeoLite MMDBs are absent; synthetic City/ASN CSV enrichment is active. Graph context uses 29 seed addresses present in the observed graph out of 40 supplied.

## API

Available routes: `GET /health`, `/dataset/summary`, `/datasets`, `/transactions`, `/transactions/{txid}`, `/wallets`, `/wallets/{wallet_id}`, `/wallets/{wallet_id}/transactions`, `/wallets/{wallet_id}/graph`, `/risk/{wallet_id}`, `/explanation/{wallet_id}`, `/alerts`, `/alerts/{alert_id}`, `/analysis/runs`, and `POST /analysis/run`. Interactive documentation is at `http://127.0.0.1:8000/docs`.

The neighborhood graph endpoint is bounded to 100 incident transactions by default and returns `nodes` and `edges`. Query parameters support pagination for listings.

## Limitations

The test period has fewer positive examples and substantially weaker positive precision/recall than validation. Ground-truth labels are from a generator, and performance does not imply real-world detection accuracy. The prototype does not implement peeling-chain, rapid forwarding, cycle, or mixing detectors; only three observed structural patterns are emitted. Synthetic city/ASN values are test fixtures and are excluded from risk scoring. No automatic GeoLite download occurs. The `POST /analysis/run` route runs synchronously and briefly closes the DuckDB connection while rebuilding tables; use the CLI for controlled training in production.
