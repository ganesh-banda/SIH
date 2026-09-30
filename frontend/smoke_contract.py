"""Check the static UI's DOM IDs and its live backend data contract."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
API="http://127.0.0.1:8000"


def fetch(path):
    with urllib.request.urlopen(API+path,timeout=10) as response:
        return json.load(response)


def main():
    html=(ROOT/"index.html").read_text(encoding="utf-8")
    script=(ROOT/"app.js").read_text(encoding="utf-8")
    ids=set(re.findall(r'\bid="([^"]+)"',html))
    ids.update(re.findall(r'<div id="([^"]+)"',script))  # nodes created while rendering
    referenced=set(re.findall(r'\$\("([^"]+)"\)',script))
    missing=referenced-ids
    assert not missing,f"JS references missing DOM IDs: {sorted(missing)}"
    assert (ROOT/"styles.css").is_file()
    summary=fetch("/dataset/summary")
    model=fetch("/model/summary")
    case=fetch("/alerts/alert_00335")
    graph=fetch("/wallets/"+case["wallet_id"]+"/graph")
    transaction=fetch("/transactions/"+case["related_transactions"][0])
    filtered=fetch("/alerts?has_pattern=true&seed_linked=true&limit=3")
    assert summary["transactions"]>0 and summary["alerts"]>0
    assert model["test"]["pr_auc"]>0
    assert case["model_evidence"] and case["patterns"] and case["graph_evidence"]
    assert graph["nodes"] and graph["edges"]
    assert transaction["txid"]==case["related_transactions"][0]
    assert all(a["patterns"] and a["graph_risk"] is not None for a in filtered)
    request=urllib.request.Request(API+"/health",headers={"Origin":"http://127.0.0.1:5173"})
    with urllib.request.urlopen(request,timeout=10) as response:
        assert response.headers["Access-Control-Allow-Origin"]=="http://127.0.0.1:5173"
    print("Frontend/API contract passed:",len(ids),"DOM IDs,",summary["alerts"],"alerts, featured case",case["alert_id"])


if __name__=="__main__":main()
