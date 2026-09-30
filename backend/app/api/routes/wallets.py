"""Address-level observations, risk, and a bounded graph neighborhood."""
from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_store
from app.api.query import one, rows, decode
from app.api.schemas import GraphResponse, RiskResponse
from app.storage.duckdb_store import DuckDBStore

router = APIRouter(tags=["wallets"])


@router.get("/wallets")
def list_wallets(limit: int = Query(50, ge=1, le=500),
                 offset: int = Query(0, ge=0), store: DuckDBStore = Depends(get_store)):
    return rows(store, "SELECT * FROM wallets ORDER BY risk_score DESC NULLS LAST,wallet_id LIMIT ? OFFSET ?", [limit,offset])


@router.get("/wallets/{wallet_id}")
def get_wallet(wallet_id: str, store: DuckDBStore = Depends(get_store)):
    return one(store, "SELECT * FROM wallets WHERE wallet_id=?", [wallet_id])


@router.get("/wallets/{wallet_id}/transactions")
def wallet_transactions(wallet_id: str, limit: int = Query(100, ge=1, le=500),
                        store: DuckDBStore = Depends(get_store)):
    one(store, "SELECT wallet_id FROM wallets WHERE wallet_id=?", [wallet_id])
    return rows(store, """SELECT wt.txid,wt.direction,wt.timestamp,p.classification_probability,
        p.anomaly_score FROM wallet_transactions wt JOIN predictions p USING(txid)
        WHERE wt.wallet_id=? ORDER BY wt.timestamp DESC LIMIT ?""", [wallet_id,limit])


@router.get("/wallets/{wallet_id}/graph", response_model=GraphResponse)
def wallet_graph(wallet_id: str, limit: int = Query(100, ge=1, le=500),
                 store: DuckDBStore = Depends(get_store)):
    one(store, "SELECT wallet_id FROM wallets WHERE wallet_id=?", [wallet_id])
    incident=rows(store,"SELECT wallet_id,txid,edge_type FROM graph_edges WHERE wallet_id=? LIMIT ?",[wallet_id,limit])
    txids=[r["txid"] for r in incident]
    if not txids: return {"nodes":[{"id":"wallet:"+wallet_id,"type":"wallet"}],"edges":[]}
    placeholders=",".join("?" for _ in txids)
    edges=rows(store,f"SELECT DISTINCT wallet_id,txid,edge_type FROM graph_edges WHERE txid IN ({placeholders}) LIMIT 1000",txids)
    wallets=sorted({r["wallet_id"] for r in edges})
    return {"nodes":[{"id":"wallet:"+a,"type":"wallet","label":a} for a in wallets]+
            [{"id":"tx:"+t,"type":"transaction","label":t} for t in sorted(set(txids))],
            "edges":[{"source":"wallet:"+e["wallet_id"] if e["edge_type"]=="input" else "tx:"+e["txid"],
                      "target":"tx:"+e["txid"] if e["edge_type"]=="input" else "wallet:"+e["wallet_id"],
                      "type":e["edge_type"]} for e in edges]}


@router.get("/risk/{wallet_id}", response_model=RiskResponse)
def wallet_risk(wallet_id: str, store: DuckDBStore = Depends(get_store)):
    return one(store, """SELECT wallet_id,risk_score,risk_category,classification_probability,
        anomaly_score,graph_risk FROM wallets WHERE wallet_id=?""",[wallet_id])


@router.get("/explanation/{wallet_id}")
def wallet_explanation(wallet_id: str, store: DuckDBStore = Depends(get_store)):
    wallet=one(store,"SELECT * FROM wallets WHERE wallet_id=?",[wallet_id])
    found=rows(store,"SELECT * FROM alerts WHERE wallet_id=? LIMIT 1",[wallet_id])
    if found:
        return decode(found[0],"patterns","model_evidence","graph_evidence","related_transactions")
    return {"wallet_id":wallet_id,"risk_score":wallet["risk_score"],
            "explanation":"No high-risk alert was generated for this address.",
            "classification_probability":wallet["classification_probability"],
            "anomaly_score":wallet["anomaly_score"],"graph_risk":wallet["graph_risk"]}
