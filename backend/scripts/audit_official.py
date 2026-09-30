"""Audit every table in the supplied synthetic Bitcoin archive."""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "reports/dataset_audit.md"
FILES = ["btc_tx_traffic.csv", "labels_transactions.csv", "labels_addresses.csv",
         "entities.csv", "peers.csv", "seed_illicit_addresses.csv"]


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    lines = ["# Dataset audit", "", "Source: attached `synthetic_btc_dataset.zip`; all files are synthetic. Amounts and fees are satoshis.", ""]
    tables = {}
    for name in FILES:
        df = pd.read_csv(RAW / name, dtype={"asn": "string"})
        tables[name] = df
        lines += [f"## {name}", "", f"Shape: {len(df):,} rows × {len(df.columns)} columns. Exact duplicate rows: {int(df.duplicated().sum()):,}.", "",
                  "| Column | Inferred type | Missing | Unique | Example |", "|---|---|---:|---:|---|"]
        for col in df:
            examples = df[col].dropna().astype(str).unique()[:2]
            ex = ", ".join(x[:65].replace("|", "\\|") + ("…" if len(x)>65 else "") for x in examples)
            lines.append(f"| `{col}` | {df[col].dtype} | {df[col].isna().sum():,} | {df[col].nunique(dropna=True):,} | {ex} |")
        lines += [""]
    tx = tables[FILES[0]]
    labels = tables[FILES[1]]
    addresses = tables[FILES[2]]
    entities = tables[FILES[3]]
    seeds = tables[FILES[5]]
    lines += ["## Field mapping", "", "`txid` identifies transactions; `timestamp` is observation time; `input_addresses` and `output_addresses` are pipe-delimited Bitcoin addresses; `src_ip` and `dst_ip` are observed network peers, not necessarily the spender or payee. `src_port`/`dst_port` are network ports. `input_amounts`, `output_amounts`, `total_input`, `total_output`, and `fee` are satoshis. `script_type` and `output_script_types` describe scripts. `geo_country` describes source IP. `asn`/`as_org` are empty. Labels come from the separate label files and never from the traffic feature table. `labels_addresses.entity_id` and `entities.entity_id` are ground-truth entity associations, reserved for evaluation. `seed_illicit_addresses` is the only known-risk seed source.", ""]
    parsed = pd.to_datetime(tx.timestamp, utc=True, errors="coerce")
    ips = pd.concat([tx.src_ip, tx.dst_ip], ignore_index=True)
    malformed = 0; nonpublic = 0
    for value in ips:
        try:
            if not ipaddress.ip_address(value).is_global: nonpublic += 1
        except ValueError: malformed += 1
    addr_values = pd.concat([tx.input_addresses, tx.output_addresses]).dropna().astype(str).str.split("|").explode()
    malformed_addr = int((~addr_values.str.match(r"^(bc1[023456789acdefghjklmnpqrstuvwxyz]{11,}|[13][1-9A-HJ-NP-Za-km-z]{25,34})$")).sum())
    lists = {}
    for side in ("input", "output"):
        counts = tx[f"{side}_addresses"].fillna("").astype(str).str.count(r"\|") + 1
        ac = tx[f"{side}_amounts"].fillna("").astype(str).str.count(r"\|") + 1
        lists[side] = (int((counts != tx[f"{side}_count"]).sum()), int((ac != tx[f"{side}_count"]).sum()))
    lines += ["## Validation and distribution", "",
              f"- Duplicate TXIDs: {tx.txid.duplicated().sum():,}; malformed TXIDs: {int((~tx.txid.astype(str).str.fullmatch('[0-9a-fA-F]{64}')).sum()):,}; transaction labels unmatched: {int((~tx.txid.isin(labels.txid)).sum()):,}.",
              f"- Invalid timestamps: {parsed.isna().sum():,}; observation range: {parsed.min()} to {parsed.max()}.",
              f"- Malformed IP occurrences: {malformed:,}; nonpublic IP occurrences: {nonpublic:,} of {len(ips):,}.",
              f"- Malformed address occurrences by syntax check (not full checksum verification): {malformed_addr:,} of {len(addr_values):,}.",
              f"- Input address/amount list length mismatch with count: {lists['input']}; output: {lists['output']}.",
              f"- Negative total_input/total_output/fee: {int(((tx[['total_input','total_output','fee']] < 0).any(axis=1)).sum()):,}; arithmetic mismatch `total_input-total_output != fee`: {int((tx.total_input-tx.total_output != tx.fee).sum()):,}; nonpositive vsize: {int((tx.vsize <= 0).sum()):,}.",
              f"- Amount (`total_output`, satoshis) percentiles: {tx.total_output.quantile([0,.25,.5,.75,.9,.99,1]).to_dict()}.",
              f"- Fee (satoshis) percentiles: {tx.fee.quantile([0,.25,.5,.75,.9,.99,1]).to_dict()}.",
              f"- Transaction label distribution: {labels.label.value_counts(dropna=False).to_dict()}; illicit share: {(labels.label.eq('illicit').mean()):.4%}.",
              f"- Address label distribution: {addresses.is_illicit.value_counts(dropna=False).to_dict()}; entity type distribution: {entities.entity_type.value_counts(dropna=False).to_dict()}.",
              f"- Known illicit seed addresses: {len(seeds):,}; seed addresses absent from address labels: {int((~seeds.address.isin(addresses.address)).sum()):,}.", "",
              "## Modelling decision", "", "Binary supervised transaction classification: `labels_transactions.label` is `licit` or `illicit`, defined by the spending input entities. `typology`, `instance_id`, `step`, `spender_entities`, `involves_illicit_output`, address/entity labels, and seed membership are excluded from classifier inputs. The source and destination IPs are observation peers, so geography cannot establish wallet ownership or illicit intent. The positive class is rare; report PR-AUC and per-class metrics. Use chronological splits and only row-local, observation-time features for predictive evaluation. Full-graph statistics and seed proximity are post-hoc context, not classifier inputs.", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
