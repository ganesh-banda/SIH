"""Observable structural patterns with thresholds fitted on training rows."""
from __future__ import annotations

import json
import pandas as pd


def fit_thresholds(train: pd.DataFrame) -> dict[str,int]:
    return {"fan_out_gt":int(train.output_count.quantile(.99)),
            "fan_in_gt":int(train.input_count.quantile(.99))}


def detect_transaction(row, thresholds: dict[str,int]) -> list[dict]:
    evidence=[]
    if row.output_count>thresholds["fan_out_gt"]:
        evidence.append({"pattern":"unusual_fan_out","output_count":int(row.output_count),
                         "training_p99":thresholds["fan_out_gt"]})
    if row.input_count>thresholds["fan_in_gt"]:
        evidence.append({"pattern":"unusual_fan_in","input_count":int(row.input_count),
                         "training_p99":thresholds["fan_in_gt"]})
    amounts=row.output_amounts
    if amounts is not None and len(amounts)>2 and len(set(amounts))==1:
        evidence.append({"pattern":"equal_value_outputs","output_count":len(amounts),
                         "amount_sats":int(amounts[0])})
    return evidence


def detect_all(transactions: pd.DataFrame, thresholds: dict[str,int]) -> list[str]:
    return [json.dumps(detect_transaction(row,thresholds)) for row in transactions.itertuples()]
