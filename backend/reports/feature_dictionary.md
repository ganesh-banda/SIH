# Feature dictionary

Model inputs are computed for one observed transaction. Address strings, TXIDs, IPs, entity IDs, labels, typologies, and future graph state never enter the model.

| Feature | Source columns | Calculation |
|---|---|---|
| input_count | input_count | Numeric count of inputs |
| output_count | output_count | Numeric count of outputs |
| total_input | total_input | Input satoshis |
| total_output | total_output | Output satoshis |
| fee | fee | Fee satoshis |
| vsize | vsize | Virtual bytes |
| fee_rate | fee_rate | Satoshis per virtual byte |
| rbf | rbf | Replace-by-fee flag |
| version | version | Transaction version |
| locktime_nonzero | locktime | One if locktime is nonzero |
| max_output_share | output_amounts | Largest output divided by output total |
| output_amount_cv | output_amounts | Population standard deviation divided by mean |
| equal_output_fraction | output_amounts | Most frequent exact output amount count divided by output count |
| unique_input_count | input_addresses | Number of distinct input addresses |
| unique_output_count | output_addresses | Number of distinct output addresses |

The imputer learns medians on training records only. These features are available when the transaction is observed, though some (fees, output composition) are transaction contents and may be highly predictive of this synthetic generator's typologies.

## Context features excluded from supervised training

| Feature | Source | Calculation |
|---|---|---|
| transaction_count | graph input/output edges | Distinct observed transactions touching an address |
| incoming_count | output_addresses | Number of received output slots |
| outgoing_count | input_addresses | Number of spent input slots |
| structural_degree | address–transaction graph | Number of neighboring transaction nodes, ignoring IP edges |
| component_size | address–transaction graph | Size of connected component |
| seed_distance_le4 | seed_illicit_addresses + graph | Shortest structural path up to four edges; null beyond |
| graph_risk | seed_distance_le4 | 1/(distance+1), contextual only |
| anomaly_score | Isolation Forest score | Negative score_samples, clipped linear scaling using training 1st/99th percentiles |
| unusual_fan_out | output_count | Count exceeds training 99th percentile |
| unusual_fan_in | input_count | Count exceeds training 99th percentile |
| equal_value_outputs | output_amounts | More than two outputs have the same amount |

Possible entity groups use common input addresses, excluding unusually large input sets and equal-output transactions. The groups suggest association only. The labelled entity file is never used to construct them.

## Unavailable or omitted

ASN and organization are empty in the archive. Real city, region, latitude, longitude, timezone and MMDB-derived ASN are unavailable until GeoLite2-City and GeoLite2-ASN databases are installed. Explicit synthetic City/ASN CSV fixtures exist for local testing and are marked `synthetic_fixture`; latitude, longitude and timezone remain null. No distance or rapid geographic-change feature is calculated. Source and destination IPs are peer observations, so unique IPs per address would be misleading. Graph betweenness/PageRank and peeling/rapid-forwarding detectors are not used in the predictive model or claims. No target-derived proximity or full-graph feature enters held-out model evaluation.
