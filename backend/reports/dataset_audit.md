# Dataset audit

Source: attached `synthetic_btc_dataset.zip`; all files are synthetic. Amounts and fees are satoshis.

## btc_tx_traffic.csv

Shape: 20,844 rows × 30 columns. Exact duplicate rows: 0.

| Column | Inferred type | Missing | Unique | Example |
|---|---|---:|---:|---|
| `timestamp` | str | 0 | 20,842 | 2024-06-01T00:00:28.340Z, 2024-06-01T00:00:34.811Z |
| `txid` | str | 0 | 20,844 | 3b0dfa168b801b8010d4f7c5dc9fc219b93788ea834bea2fe5d93ac895887258, d83952c13f1a9cb7277330fc676e3ce0e3df3fde89bff9780cf6aadaf50c3c23 |
| `src_ip` | str | 0 | 600 | 34.124.76.103, 195.75.21.130 |
| `src_port` | int64 | 0 | 1,748 | 54590, 35150 |
| `dst_ip` | str | 0 | 4 | 123.0.195.61, 185.217.231.147 |
| `dst_port` | int64 | 0 | 593 | 8333, 50545 |
| `geo_country` | str | 0 | 63 | ES, GB |
| `asn` | string | 20,844 | 0 |  |
| `as_org` | float64 | 20,844 | 0 |  |
| `peer_user_agent` | str | 0 | 9 | /Satoshi:0.21.1/, /Satoshi:26.0.0/ |
| `block_height` | int64 | 0 | 212 | 846129, 846130 |
| `block_time` | str | 0 | 212 | 2024-06-01T00:01:16.000Z, 2024-06-01T00:10:45.000Z |
| `is_coinbase` | int64 | 0 | 1 | 0 |
| `version` | int64 | 0 | 2 | 2, 1 |
| `locktime` | int64 | 0 | 203 | 846128, 0 |
| `rbf` | int64 | 0 | 2 | 0, 1 |
| `input_count` | int64 | 0 | 36 | 1, 31 |
| `output_count` | int64 | 0 | 28 | 8, 2 |
| `input_prevouts` | str | 0 | 20,844 | 6575caecd24011c75c0be927348d59b9d2bc7756b903ebc314931b6391e0d4a9:…, 9f6c261cd9dccce1d923da3e761549c4e1f19ce1205751d43fc08c98976c7d08:… |
| `input_addresses` | str | 0 | 20,592 | bc1p3x2zfh9cgy7a3g26cza38ee8gp4k8a3rwkqqvtwqd2p8z6amn76qnweqd9, 1XewXYu413m8196XwhqpqrfYumN9rmcW1 |
| `input_amounts` | str | 0 | 20,319 | 883236871, 29438186 |
| `output_addresses` | str | 0 | 20,840 | bc1p657gms70pa77q63n9ert5ejtw99dr4u00ekr5qek966kx6u7q6vqqtq4fy\|bc…, bc1qmnt502zpgk2lt6zdu6smyt2l73x5ajqye2vv5k\|1NUtx2y6gGBVNuMT6rq3xT… |
| `output_amounts` | str | 0 | 20,835 | 110404414\|110404414\|110404414\|110404414\|110404414\|110404414\|11040…, 2460806\|26976783 |
| `output_script_types` | str | 0 | 1,399 | p2tr\|p2tr\|p2tr\|p2tr\|p2tr\|p2tr\|p2tr\|p2tr, p2wpkh\|p2pkh |
| `script_type` | str | 0 | 4 | p2tr, p2pkh |
| `total_input` | int64 | 0 | 20,317 | 883236871, 29438186 |
| `total_output` | int64 | 0 | 20,830 | 883235312, 29437589 |
| `fee` | int64 | 0 | 2,824 | 1559, 597 |
| `vsize` | int64 | 0 | 826 | 412, 223 |
| `fee_rate` | float64 | 0 | 402 | 3.78, 2.68 |

## labels_transactions.csv

Shape: 20,844 rows × 7 columns. Exact duplicate rows: 0.

| Column | Inferred type | Missing | Unique | Example |
|---|---|---:|---:|---|
| `txid` | str | 0 | 20,844 | 3b0dfa168b801b8010d4f7c5dc9fc219b93788ea834bea2fe5d93ac895887258, d83952c13f1a9cb7277330fc676e3ce0e3df3fde89bff9780cf6aadaf50c3c23 |
| `label` | str | 0 | 2 | illicit, licit |
| `typology` | str | 0 | 12 | fan_out_split, payment |
| `instance_id` | str | 19,396 | 150 | fan_out_split_0001, peeling_chain_0001 |
| `step` | int64 | 0 | 20 | 0, 1 |
| `spender_entities` | str | 0 | 2,473 | illicit_00006, user_00913 |
| `involves_illicit_output` | int64 | 0 | 2 | 1, 0 |

## labels_addresses.csv

Shape: 65,614 rows × 5 columns. Exact duplicate rows: 0.

| Column | Inferred type | Missing | Unique | Example |
|---|---|---:|---:|---|
| `address` | str | 0 | 65,614 | 15vQBFp7ypqTKFUgSJYwFmfhyY8pJfWgDY, 15oaPPmmTj34fRuzXrtibW3xjPF7YhPPSW |
| `entity_id` | str | 1,464 | 2,083 | user_00000, user_00001 |
| `entity_type` | str | 0 | 5 | user, merchant |
| `is_illicit` | int64 | 0 | 2 | 0, 1 |
| `script_type` | str | 0 | 5 | p2pkh, p2wpkh |

## entities.csv

Shape: 2,083 rows × 6 columns. Exact duplicate rows: 0.

| Column | Inferred type | Missing | Unique | Example |
|---|---|---:|---:|---|
| `entity_id` | str | 0 | 2,083 | user_00000, user_00001 |
| `entity_type` | str | 0 | 4 | user, merchant |
| `is_illicit` | int64 | 0 | 2 | 0, 1 |
| `script_type` | str | 0 | 4 | p2pkh, p2wpkh |
| `home_peer_ip` | str | 1,427 | 402 | 179.252.6.167, 52.93.126.196 |
| `address_count` | int64 | 0 | 85 | 28, 30 |

## peers.csv

Shape: 604 rows × 6 columns. Exact duplicate rows: 0.

| Column | Inferred type | Missing | Unique | Example |
|---|---|---:|---:|---|
| `ip` | str | 0 | 604 | 103.93.62.87, 149.6.139.117 |
| `role` | str | 0 | 2 | sensor, peer |
| `geo_country` | str | 0 | 63 | JP, DE |
| `asn` | string | 604 | 0 |  |
| `as_org` | float64 | 604 | 0 |  |
| `user_agent` | str | 0 | 9 | /Satoshi:24.0.1/, /Satoshi:26.0.0/ |

## seed_illicit_addresses.csv

Shape: 40 rows × 3 columns. Exact duplicate rows: 0.

| Column | Inferred type | Missing | Unique | Example |
|---|---|---:|---:|---|
| `address` | str | 0 | 40 | 33aBBAxym6ZemdxBpRbuh4aogTj8yeDZ8U, 36L4woumegq8H6LyfZpU27VmG6hNVMuUmB |
| `entity_id` | str | 0 | 11 | illicit_00000, illicit_00002 |
| `source` | str | 0 | 1 | known_funding_address |

## Field mapping

`txid` identifies transactions; `timestamp` is observation time; `input_addresses` and `output_addresses` are pipe-delimited Bitcoin addresses; `src_ip` and `dst_ip` are observed network peers, not necessarily the spender or payee. `src_port`/`dst_port` are network ports. `input_amounts`, `output_amounts`, `total_input`, `total_output`, and `fee` are satoshis. `script_type` and `output_script_types` describe scripts. `geo_country` describes source IP. `asn`/`as_org` are empty. Labels come from the separate label files and never from the traffic feature table. `labels_addresses.entity_id` and `entities.entity_id` are ground-truth entity associations, reserved for evaluation. `seed_illicit_addresses` is the only known-risk seed source.

## Validation and distribution

- Duplicate TXIDs: 0; malformed TXIDs: 0; transaction labels unmatched: 0.
- Invalid timestamps: 0; observation range: 2024-06-01 00:00:28.340000+00:00 to 2024-06-02 15:55:02.659000+00:00.
- Malformed IP occurrences: 0; nonpublic IP occurrences: 0 of 41,688.
- Malformed address occurrences by syntax check (not full checksum verification): 0 of 104,554.
- Input address/amount list length mismatch with count: (0, 0); output: (0, 0).
- Negative total_input/total_output/fee: 0; arithmetic mismatch `total_input-total_output != fee`: 0; nonpositive vsize: 0.
- Amount (`total_output`, satoshis) percentiles: {0.0: 8793.0, 0.25: 8588980.25, 0.5: 22024328.0, 0.75: 48479220.25, 0.9: 562358467.900003, 0.99: 89239111011.58, 1.0: 99920188599.0}.
- Fee (satoshis) percentiles: {0.0: 111.0, 0.25: 372.0, 0.5: 567.0, 0.75: 873.0, 0.9: 1573.0, 0.99: 4289.57, 1.0: 13507.0}.
- Transaction label distribution: {'licit': 19524, 'illicit': 1320}; illicit share: 6.3328%.
- Address label distribution: {0: 63916, 1: 1698}; entity type distribution: {'user': 2000, 'merchant': 50, 'illicit': 25, 'exchange': 8}.
- Known illicit seed addresses: 40; seed addresses absent from address labels: 0.

## Modelling decision

Binary supervised transaction classification: `labels_transactions.label` is `licit` or `illicit`, defined by the spending input entities. `typology`, `instance_id`, `step`, `spender_entities`, `involves_illicit_output`, address/entity labels, and seed membership are excluded from classifier inputs. The source and destination IPs are observation peers, so geography cannot establish wallet ownership or illicit intent. The positive class is rare; report PR-AUC and per-class metrics. Use chronological splits and only row-local, observation-time features for predictive evaluation. Full-graph statistics and seed proximity are post-hoc context, not classifier inputs.
