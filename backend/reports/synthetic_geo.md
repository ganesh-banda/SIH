# Synthetic geolocation fixtures

The local test fixtures `data/geolite/Synthetic-City.csv` and `Synthetic-ASN.csv` cover all **604** public IPs in the supplied synthetic traffic and peer tables. They are CSV lookup tables, **not MaxMind GeoLite MMDB files**. Do not rename or present them as GeoLite databases.

Country ISO codes come from the dataset's `peers.csv`; the generator verifies that every traffic IP appears there and each source-IP country agrees with `btc_tx_traffic.csv`. Country names are left as ISO codes. The city and region labels, ASN numbers and ASN organization names are generated test values. Latitude, longitude and timezone are empty because there is no defensible location for invented cities.

Regenerate deterministically:

```powershell
.\env\Scripts\python.exe -m scripts.create_synthetic_geo
```

Synthetic mode is enabled locally by `BTCRISK_USE_SYNTHETIC_GEO=true` in `.env`. The API and training pipeline prefer actual local MMDB files if either is installed; otherwise they use these fixtures only when that flag is true. Lookup responses and normalized transaction columns carry `data_source: synthetic_fixture`. `/health` stays degraded and identifies the synthetic fixture, so this cannot be mistaken for installed GeoLite data. Private, reserved and malformed IP handling is unchanged.

The current analysis run enriched all 20,844 transactions for both source and destination IP. Source country codes match the dataset, and destination ASN is present for all rows. The 15 ML inputs remain unchanged and exclude geography and ASN. The model evaluation results are therefore unchanged. Do not use the invented city or ASN values for geospatial or ownership conclusions.
