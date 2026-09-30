"""Ranked, locally persisted investigator alerts."""
from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_store
from app.api.query import rows, one, decode
from app.storage.duckdb_store import DuckDBStore

router=APIRouter(prefix="/alerts",tags=["alerts"])


@router.get("")
def list_alerts(limit:int=Query(50,ge=1,le=500),offset:int=Query(0,ge=0),
                search:str|None=Query(None,max_length=128),
                has_pattern:bool=False,seed_linked:bool=False,
                store:DuckDBStore=Depends(get_store)):
    conditions=[]
    params=[]
    if search:
        conditions.append("strpos(lower(wallet_id), lower(?)) > 0")
        params.append(search.strip())
    if has_pattern: conditions.append("patterns != '[]'")
    if seed_linked: conditions.append("graph_risk IS NOT NULL")
    where=" WHERE "+" AND ".join(conditions) if conditions else ""
    return [decode(r,"patterns","model_evidence","graph_evidence","related_transactions") for r in
            rows(store,"SELECT * FROM alerts"+where+" ORDER BY risk_score DESC,wallet_id LIMIT ? OFFSET ?",params+[limit,offset])]


@router.get("/{alert_id}")
def get_alert(alert_id:str,store:DuckDBStore=Depends(get_store)):
    return decode(one(store,"SELECT * FROM alerts WHERE alert_id=?",[alert_id]),
                  "patterns","model_evidence","graph_evidence","related_transactions")
