"""Analysis-run endpoints.

``GET /analysis/runs`` works now (reads run metadata from DuckDB).
``POST /analysis/run`` is pending the full pipeline. TODO(dataset).
"""

import subprocess
import sys
from fastapi import APIRouter, Depends, Query, Request, HTTPException

from app.api.dependencies import get_store
from app.config import BACKEND_ROOT
from app.storage.duckdb_store import DuckDBStore

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/runs")
def list_runs(limit: int = Query(20, ge=1, le=200),
              store: DuckDBStore = Depends(get_store)) -> list[dict]:
    frame = store.list_runs(limit)
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}
            for row in frame.to_dicts()]


@router.post("/run")
def run_analysis(request: Request):
    """Explicitly rerun analysis; the API never retrains on startup."""
    store = request.app.state.store
    run_id = store.start_run(source_file="btc_tx_traffic.csv")
    store.close()
    result = None
    try:
        result = subprocess.run([sys.executable, "-m", "app.models.train"],
                                cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Analysis exceeded ten minutes") from exc
    finally:
        request.app.state.store = DuckDBStore(request.app.state.settings.duckdb_path)
        request.app.state.store.init_schema()
        request.app.state.store.finish_run(run_id, "completed" if result and result.returncode == 0 else "failed")
    if result.returncode:
        raise HTTPException(500, {"detail":"Analysis failed", "stderr":result.stderr[-2000:]})
    return {"run_id":run_id,"status":"completed","output":result.stdout.strip()}
