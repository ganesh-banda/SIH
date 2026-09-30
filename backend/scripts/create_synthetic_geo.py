"""Generate clearly marked local geo test fixtures for observed dataset IPs.

Country codes are copied from peers.csv; cities and ASNs are invented test
values. No external geolocation lookup or network access is performed.
"""
from __future__ import annotations

import csv
import ipaddress
from pathlib import Path

from app.config import get_settings


def main() -> None:
    settings=get_settings()
    raw=settings.raw_dir
    destination=settings.data_dir/"geolite"
    destination.mkdir(parents=True,exist_ok=True)
    with (raw/"peers.csv").open(newline="",encoding="utf-8") as handle:
        peers=list(csv.DictReader(handle))
    by_ip={}
    for row in peers:
        ip=str(ipaddress.ip_address(row["ip"]))
        if not ipaddress.ip_address(ip).is_global:
            raise ValueError(f"Nonpublic peer IP: {ip}")
        if ip in by_ip: raise ValueError(f"Duplicate peer IP: {ip}")
        by_ip[ip]=row["geo_country"]
    seen=set()
    with (raw/"btc_tx_traffic.csv").open(newline="",encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            src,dst=row["src_ip"],row["dst_ip"]
            seen.update((src,dst))
            if src not in by_ip or dst not in by_ip:
                raise ValueError("Traffic IP missing from peers.csv")
            if row["geo_country"]!=by_ip[src]:
                raise ValueError(f"Source country mismatch for {src}")
    if seen!=set(by_ip):
        raise ValueError("Peer table and traffic IP sets differ")
    city_path=destination/"Synthetic-City.csv"
    asn_path=destination/"Synthetic-ASN.csv"
    with city_path.open("w",newline="",encoding="utf-8") as city_file, asn_path.open("w",newline="",encoding="utf-8") as asn_file:
        city=csv.DictWriter(city_file,fieldnames=["ip","country_iso","country","region","city","latitude","longitude","timezone","source"])
        asn=csv.DictWriter(asn_file,fieldnames=["ip","asn","asn_org","source"])
        city.writeheader(); asn.writeheader()
        for index,ip in enumerate(sorted(by_ip),start=1):
            iso=by_ip[ip]
            city.writerow({"ip":ip,"country_iso":iso,"country":iso,"region":"Synthetic test region",
                           "city":f"Synthetic test city {index:04d}","latitude":"","longitude":"",
                           "timezone":"","source":"synthetic_fixture"})
            asn.writerow({"ip":ip,"asn":4200000000+index,
                          "asn_org":f"Synthetic test network {index:04d}","source":"synthetic_fixture"})
    print(f"Created {len(by_ip)} IP records in {city_path} and {asn_path}")


if __name__=="__main__": main()
