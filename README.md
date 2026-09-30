# Tracepoint: Bitcoin risk investigation demo

An offline investigation workspace for the supplied **synthetic** Bitcoin transaction dataset. The repository includes a trained backend snapshot and a dependency-free frontend. Alerts prioritize human review; they do not identify criminals or prove ownership of an address.

## Run the demo

Python 3.11+ is required. In two terminals from the repository root:

```powershell
# Terminal 1 — backend
cd backend
python -m venv env
.\env\Scripts\python.exe -m pip install -r requirements-ml.txt
Copy-Item .env.example .env
.\env\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — frontend (uses Python's static server, no npm install)
cd frontend
python -m http.server 5173 --bind 127.0.0.1
```

Open **http://127.0.0.1:5173**. Click **open the workspace**, then **open featured case** to follow an alert through its score, backend explanation, SHAP contributors, transaction graph, history, and network observation. Search the saved data by address or 64-character TXID. Click **↗** in the header to change the API URL.

The saved DuckDB, Parquet, model, raw-data, and synthetic geo files are included for this demo. API startup reads the saved results; it does not train again. To reproduce the analysis from the supplied CSVs, run `python -m scripts.audit_official`, `python -m scripts.create_synthetic_geo`, then `python -m app.models.train` inside `backend/`. Training takes about a minute on the development machine. Use `python -m pytest -q` for the backend suite. With the API running, `python frontend/smoke_contract.py` checks the frontend/API handoff.

The frontend is the existing dependency-free HTML/CSS/JavaScript app. The redesign takes its visual direction from [Kivi](https://heykivi.ai/): deep forest surfaces, large serif headings, lime accents, floating cards, and cream content panels. Tracepoint uses its own content, CSS art, and product identity. The API base URL is centralized in `frontend/app.js`; set `window.TRACEPOINT_API_BASE_URL` before that script loads to override its default, or use the header setting (stored only in your browser).

To run the browser end-to-end test, keep both servers running and launch Edge headless with a DevTools port, then run:

```powershell
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --disable-gpu --remote-debugging-port=9222 --user-data-dir="$(Join-Path $PWD 'frontend\.browser-e2e')" about:blank
# In another terminal, from backend/:
.\env\Scripts\python.exe ..\frontend\browser_e2e.py
```

The browser test covers the dashboard, alerts, address and TXID lookup, investigation, graph node selection and zoom, API failure/recovery, and widths of 1440, 1024, 768, and 390 pixels. Screenshots are written under the ignored `frontend/.browser-results/` directory.

## What the demo shows

- 20,844 synthetic transactions, 64,414 addresses, and 1,877 prioritized alerts.
- An XGBoost transaction detector with held-out test PR-AUC **0.377**. At the validation-chosen threshold, test illicit precision is **0.402** and recall **0.500**.
- Separate Isolation Forest anomaly scores, transaction graph context, configurable structural patterns, and SHAP contributions in model log-odds.
- Local City and ASN **synthetic CSV fixtures**. They are explicitly labelled as test data and are not MaxMind MMDB files. Their city and ASN values do not enter the model or final risk score.

See [the backend report](backend/reports/final_report.md), [dataset audit](backend/reports/dataset_audit.md), [synthetic geo provenance](backend/reports/synthetic_geo.md), and [demo checklist](DEMO_CHECKLIST.md). The frontend is static HTML/CSS/JavaScript and calls the local FastAPI service through HTTP. It has no remote scripts, fonts, maps, or hosted inference.

## Repository contents

```
frontend/                 static investigation workspace
backend/app/              FastAPI, ingestion, ML, graph, patterns, storage
backend/data/raw/         supplied synthetic dataset and MaxMind notices
backend/data/geolite/     clearly marked synthetic City / ASN CSV fixtures
backend/data/processed/   normalized transaction snapshot
backend/data/features/    model and graph feature snapshots
backend/data/results/     DuckDB, predictions, alerts, graph tables
backend/models/           trained model artifacts and feature schema
backend/reports/          audit, evaluation, feature dictionary, plots
backend/tests/            pytest suite
```

The virtual environment, machine-specific `.env`, logs, and licensed `.mmdb` files are excluded from Git. The original synthetic archive can be reimported with `python -m scripts.import_archive <archive-path>`; all original archive members used here are already under `backend/data/raw/`.

## Boundaries

This is a **batch-data research prototype**, not a live Bitcoin monitor. The displayed address score is 100 times its highest-scored observed spending transaction probability; it is not a calibrated probability of criminal conduct. The synthetic dataset and geo fixtures are unsuitable for real investigations. `POST /analysis/run` retrains synchronously and temporarily closes the DuckDB connection, so use the saved snapshot while presenting the frontend.

The MaxMind attribution and supplied GeoLite notices are preserved in [NOTICE.md](NOTICE.md) and `backend/data/raw/`. Review the [current GeoLite EULA](https://www.maxmind.com/en/geolite/eula) before distributing derivatives of GeoLite data.
