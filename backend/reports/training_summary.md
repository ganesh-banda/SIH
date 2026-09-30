# Training summary

```json
{
  "seed": 20240601,
  "features": [
    "input_count",
    "output_count",
    "total_input",
    "total_output",
    "fee",
    "vsize",
    "fee_rate",
    "rbf",
    "version",
    "locktime_nonzero",
    "max_output_share",
    "output_amount_cv",
    "equal_output_fraction",
    "unique_input_count",
    "unique_output_count"
  ],
  "split": "chronological_60_20_20",
  "train_rows": 12506,
  "validation_rows": 4169,
  "test_rows": 4169,
  "high_probability_threshold": 0.6781997680664065,
  "medium_probability_threshold": 0.33909988403320324,
  "risk_method": "100 * maximum XGBoost probability of transactions spent by address",
  "anomaly_normalization": {
    "training_p01": 0.3512798911492988,
    "training_p99": 0.6646734425793218
  },
  "pattern_thresholds": {
    "fan_out_gt": 27,
    "fan_in_gt": 10
  },
  "graph_summary": {
    "nodes": 85862,
    "edges": 146242,
    "wallet": 64414,
    "tx": 20844,
    "ip": 604,
    "entity": 0
  },
  "seed_nodes_present": 29,
  "source_sha256": "c1515715d5d2487b7ee105fc9c40694735c022e1cc7101be3b9993bf39858ca4",
  "geolite_status": "synthetic_fixture"
}
```

Risk is based on supervised transaction probability only. Anomaly, seed proximity and patterns stay independent evidence. This is not a calibrated wallet-criminality probability.
