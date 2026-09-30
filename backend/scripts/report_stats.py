"""Small factual snapshot for the final report."""
import json
from app.config import get_settings
from app.storage.duckdb_store import DuckDBStore


def main():
    with DuckDBStore(get_settings().duckdb_path,read_only=True) as db:
        queries={
            "risk_categories":"SELECT risk_category,count(*) n FROM wallets GROUP BY 1 ORDER BY 1",
            "pattern_counts":"""SELECT count(*) FILTER (WHERE patterns LIKE '%unusual_fan_out%') fan_out,
                count(*) FILTER (WHERE patterns LIKE '%unusual_fan_in%') fan_in,
                count(*) FILTER (WHERE patterns LIKE '%equal_value_outputs%') equal_value FROM predictions""",
            "entities":"SELECT count(*) wallets,count(DISTINCT possible_entity_group) candidate_groups FROM entity_candidates",
            "seed_reached":"SELECT count(*) reached FROM wallets WHERE graph_risk IS NOT NULL",
            "alert_example":"SELECT * FROM alerts ORDER BY risk_score DESC,wallet_id LIMIT 1",
            "demo_candidates":"SELECT alert_id,wallet_id,risk_score,patterns,graph_risk FROM alerts WHERE patterns != '[]' AND graph_risk IS NOT NULL AND graph_risk < 1 ORDER BY risk_score DESC LIMIT 5"}
        for name,sql in queries.items():
            print(name,json.dumps(db.query(sql).to_dicts(),default=str))


if __name__=="__main__": main()
