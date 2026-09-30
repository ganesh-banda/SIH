# Data provenance and attribution

The Bitcoin transactions, labels, entities, peers, and seeds in `backend/data/raw/` are the supplied **synthetic** dataset. The dataset README states that its public-IP country assignments were sampled from GeoLite2-Country blocks. The archive also includes `GEOLITE_COPYRIGHT.txt` and `GEOLITE_LICENSE.txt`; those notices are preserved unchanged.

This product includes GeoLite Data created by MaxMind, available from https://www.maxmind.com.

The files `backend/data/geolite/Synthetic-City.csv` and `Synthetic-ASN.csv` are test fixtures generated in this project. Their country codes are copied from the supplied peer table; their city/region labels, ASN numbers, and organization names are invented test values. They are not MaxMind GeoLite databases.

No real Bitcoin wallet, private key, or intercepted traffic is included. The displayed risk scores are generated for this synthetic dataset only.
