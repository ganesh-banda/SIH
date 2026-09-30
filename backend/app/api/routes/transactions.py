"""Observed transaction listing and details."""
from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_store
from app.api.query import rows, one, decode
from app.storage.duckdb_store import DuckDBStore

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def list_transactions(limit: int = Query(50, ge=1, le=500),
                      offset: int = Query(0, ge=0),
                      store: DuckDBStore = Depends(get_store)):
    return rows(store, """SELECT t.txid,t.timestamp,t.input_count,t.output_count,t.total_output,t.fee,
        p.classification_probability,p.anomaly_score,p.patterns
        FROM transactions t JOIN predictions p USING(txid)
        ORDER BY t.timestamp,t.txid LIMIT ? OFFSET ?""", [limit, offset])


@router.get("/{txid}")
def get_transaction(txid: str, store: DuckDBStore = Depends(get_store)):
    record = one(store, "SELECT t.*,p.classification_probability,p.anomaly_score,p.patterns,p.model_evidence FROM transactions t JOIN predictions p USING(txid) WHERE txid=?", [txid])
    return decode(record, "patterns", "model_evidence")
