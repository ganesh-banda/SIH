"""Exercise persisted-data endpoints; pass --rerun to check POST /analysis/run."""
from __future__ import annotations

import sys
from fastapi.testclient import TestClient
from app.main import app


def main():
    with TestClient(app) as client:
        if "--rerun" in sys.argv:
            response=client.post("/analysis/run")
            assert response.status_code==200,response.text
        summary=client.get("/dataset/summary")
        assert summary.status_code==200,summary.text
        model=client.get("/model/summary")
        assert model.status_code==200,model.text
        assert model.json()["test"]["pr_auc"]>0
        filtered=client.get("/alerts?has_pattern=true&seed_linked=true&limit=3")
        assert filtered.status_code==200,filtered.text
        assert all(a["patterns"] and a["graph_risk"] is not None for a in filtered.json())
        first_tx=client.get("/transactions").json()[0]["txid"]
        first_alert=client.get("/alerts").json()[0]
        wallet=first_alert["wallet_id"]
        paths=["/health","/transactions/"+first_tx,"/wallets","/wallets/"+wallet,
               "/wallets/"+wallet+"/transactions","/wallets/"+wallet+"/graph",
               "/risk/"+wallet,"/explanation/"+wallet,"/alerts/"+first_alert["alert_id"]]
        for path in paths:
            response=client.get(path)
            assert response.status_code==200,(path,response.text)
        print("API smoke passed:",summary.json(),len(paths)+3,"routes")


if __name__=="__main__": main()
