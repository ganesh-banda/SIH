#!/usr/bin/env python3
"""Synthetic Bitcoin P2P transaction-traffic generator (SIH PS-5).

Produces a dataset in the exact 30-column format of the official
``btc_tx_traffic.csv`` sample, plus SEPARATE ground-truth label files.

What is REAL / VERIFIED vs what is a SYNTHETIC ASSUMPTION
---------------------------------------------------------
Taken from real reference data or protocol rules (not invented):
  * IP -> country: every IP is sampled from a GeoLite2-Country block whose
    ``geoname_id`` maps to an ISO code, and is re-verified against an
    independent lookup of the same GeoLite files after generation.
  * Addresses: syntactically valid Base58Check (P2PKH/P2SH) and
    Bech32/Bech32m (P2WPKH/P2WSH/P2TR) encodings with correct checksums,
    built from random hashes (no real keys, no real wallets).
  * vsize: standard per-script vbyte sizes; this model reproduces the vsize
    of every fully-readable row in the official sample exactly.
  * fee = total_input - total_output, fee_rate = fee/vsize (2 decimals),
    totals = sums of per-input/per-output amounts (satoshi integers),
    as observed in the official sample.
  * UTXO correctness: each output is spent at most once; every prevout
    points at an earlier output with matching owner and amount.
  * Block timing: exponential inter-block times with the 600 s protocol
    target; tx confirmation block is after the observation time and never
    before the block of any parent tx.
  * Anti-fee-sniping locktime = chain tip at broadcast (seen in the sample).
  * Ephemeral ports in the Linux default range 32768-60999; peers on 8333.
  * Peer user agents are real Bitcoin Core release strings.

Synthetic ASSUMPTIONS (all in Config, all printed to generation_metadata.json):
  entity counts, balances, payment sizes, fee-rate range, tx arrival rate,
  typology parameters, fraction of entities running their own node, ...
  These are modelling choices, NOT real-world statistics.

Deliberately NOT done:
  * Geography, IP, ports, user agent and script type are drawn the same way
    for licit and illicit entities, so they carry no label information.
    Only transaction-graph behaviour differs by label.
  * asn / as_org are left empty unless a GeoLite2-ASN CSV is supplied
    (the GeoLite2-Country database contains no ASN data).
  * No coinbase rows: block rewards are not relayed as loose P2P tx messages.

Labels are written to separate files so the traffic file matches the
official (unlabelled) schema.

Usage:
  python generate_btc_dataset.py --geolite-dir ./geolite --out ./dataset
  python generate_btc_dataset.py --geolite-dir ./geolite --asn-csv ./GeoLite2-ASN-Blocks-IPv4.csv

Requires only the Python 3.10+ standard library.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import heapq
import ipaddress
import json
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

# =============================================================================
# Configuration (every synthetic assumption lives here)
# =============================================================================


@dataclass
class Config:
    seed: int = 20240601
    start_time: str = "2024-06-01T00:00:00Z"
    hours: float = 36.0
    normal_tx_per_hour: float = 540.0  # density matches the official sample (~8 tx / 53 s)

    # --- chain -------------------------------------------------------------
    start_block_height: int = 846129      # first block after start_time (as in the sample)
    block_interval_s: float = 600.0       # protocol target
    p_confirm_next_block: float = 0.7     # else waits geometrically more blocks
    p_anti_fee_sniping: float = 0.3       # locktime = tip height, else 0
    p_rbf: float = 0.3
    p_version_1: float = 0.15             # else version 2
    fee_rate_range: tuple[float, float] = (1.0, 5.0)  # sat/vB; range seen in the sample
    dust_limit: int = 546

    # --- network -----------------------------------------------------------
    n_sensors: int = 4                    # the sample shows a handful of repeated dst_ip
    n_peers: int = 600
    ipv6_fraction: float = 0.0            # the sample shows IPv4 only
    country_weighting: str = "address_space"  # or "uniform"
    p_sensor_outbound: float = 0.25       # sensor dialled the peer -> src_port 8333
    p_own_node: float = 0.3               # users/illicit: broadcast via own node
    p_own_node_service: float = 1.0       # exchanges/merchants run their own node
    p_use_own_node: float = 0.85          # else a random peer relays first
    extra_observation_prob: float = 0.0   # >0 => same tx also seen via other peers
    user_agents: tuple[str, ...] = (
        "/Satoshi:0.21.1/", "/Satoshi:22.0.0/", "/Satoshi:23.0.0/", "/Satoshi:24.0.1/",
        "/Satoshi:25.0.0/", "/Satoshi:25.1.0/", "/Satoshi:26.0.0/", "/Satoshi:26.1.0/",
        "/Satoshi:27.0.0/",
    )

    # --- entities (identical script-type distribution for every entity type) --
    n_users: int = 2000
    n_merchants: int = 50
    n_exchanges: int = 8
    n_illicit: int = 25
    script_type_weights: dict[str, float] = field(default_factory=lambda: {
        "p2wpkh": 0.55, "p2sh": 0.15, "p2pkh": 0.15, "p2tr": 0.15})
    p_fresh_receive_address: float = 0.85  # else reuse an existing address
    # genesis funding (UTXOs that pre-date the dataset): (count range, sat range)
    funding: dict[str, tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=lambda: {
        "user": ((1, 3), (100_000, 50_000_000)),
        "merchant": ((1, 3), (1_000_000, 100_000_000)),
        "exchange": ((60, 150), (10_000_000, 5_000_000_000)),
        "illicit": ((2, 5), (10_000_000, 1_000_000_000)),
    })

    # --- licit activity mix ---------------------------------------------------
    normal_action_weights: dict[str, float] = field(default_factory=lambda: {
        "payment": 0.76, "sweep": 0.08, "exchange_batch": 0.07, "consolidation": 0.07,
        "coinjoin": 0.02})
    recipient_weights: dict[str, float] = field(default_factory=lambda: {
        "user": 0.55, "merchant": 0.2, "exchange": 0.15, "external": 0.10})
    external_script_types: tuple[str, ...] = ("p2wpkh", "p2sh", "p2pkh", "p2tr", "p2wsh")

    # --- illicit typologies: instances per 36 h (scaled with --hours) ---------
    typology_instances: dict[str, int] = field(default_factory=lambda: {
        "peeling_chain": 30, "fan_out_split": 25, "ransomware": 10,
        "rapid_layering": 40, "circular": 20, "illicit_coinjoin": 15})
    peel_steps: tuple[int, int] = (5, 20)
    peel_fraction: tuple[float, float] = (0.01, 0.15)
    peel_delay_mean_s: float = 900.0
    split_width: tuple[int, int] = (8, 25)
    split_forward_delay_mean_s: float = 1800.0
    ransom_victims: tuple[int, int] = (5, 20)
    ransom_amount: tuple[int, int] = (2_000_000, 20_000_000)
    ransom_window_s: float = 6 * 3600.0
    layering_hops: tuple[int, int] = (3, 10)
    layering_delay_mean_s: float = 120.0
    circular_hops: tuple[int, int] = (3, 6)
    circular_delay_mean_s: float = 600.0
    coinjoin_participants: tuple[int, int] = (5, 10)
    coinjoin_denominations: tuple[int, ...] = (100_000, 1_000_000, 5_000_000, 50_000_000)
    seed_fraction: float = 0.3  # share of illicit entities whose funding addresses are "known"


# =============================================================================
# Bitcoin encodings (BIP-13/BIP-173/BIP-350) and size model
# =============================================================================

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32_CONST, BECH32M_CONST = 1, 0x2BC830A3


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def base58check_encode(version: int, payload: bytes) -> str:
    raw = bytes([version]) + payload
    raw += sha256d(raw)[:4]
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return "1" * pad + out


def base58check_decode(text: str) -> tuple[int, bytes]:
    n = 0
    for ch in text:
        n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    raw = b"\0" * (len(text) - len(text.lstrip("1"))) + raw
    body, check = raw[:-4], raw[-4:]
    if sha256d(body)[:4] != check:
        raise ValueError("bad base58 checksum")
    return body[0], body[1:]


def _polymod(values: list[int]) -> int:
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (b >> i) & 1 else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data: bytes, frm: int, to: int) -> list[int]:
    acc = bits = 0
    out = []
    for value in data:
        acc = (acc << frm) | value
        bits += frm
        while bits >= to:
            bits -= to
            out.append((acc >> bits) & ((1 << to) - 1))
    if bits:
        out.append((acc << (to - bits)) & ((1 << to) - 1))
    return out


def segwit_encode(hrp: str, witver: int, program: bytes) -> str:
    const = BECH32_CONST if witver == 0 else BECH32M_CONST
    data = [witver] + _convertbits(program, 8, 5)
    pm = _polymod(_hrp_expand(hrp) + data + [0] * 6) ^ const
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32_CHARSET[d] for d in data + checksum)


def segwit_checksum_ok(address: str) -> bool:
    hrp, _, data_part = address.rpartition("1")
    data = [BECH32_CHARSET.index(c) for c in data_part]
    const = BECH32_CONST if data[0] == 0 else BECH32M_CONST
    return _polymod(_hrp_expand(hrp) + data) == const


def make_address(script_type: str, rng: random.Random) -> str:
    if script_type == "p2pkh":
        return base58check_encode(0x00, rng.randbytes(20))
    if script_type == "p2sh":
        return base58check_encode(0x05, rng.randbytes(20))
    if script_type == "p2wpkh":
        return segwit_encode("bc", 0, rng.randbytes(20))
    if script_type == "p2wsh":
        return segwit_encode("bc", 0, rng.randbytes(32))
    if script_type == "p2tr":
        return segwit_encode("bc", 1, rng.randbytes(32))
    raise ValueError(script_type)


def address_is_valid(address: str, script_type: str) -> bool:
    try:
        if script_type in ("p2pkh", "p2sh"):
            version, payload = base58check_decode(address)
            return len(payload) == 20 and version == (0x00 if script_type == "p2pkh" else 0x05)
        expected = {"p2wpkh": ("bc1q", 42), "p2wsh": ("bc1q", 62), "p2tr": ("bc1p", 62)}[script_type]
        return address.startswith(expected[0]) and len(address) == expected[1] \
            and segwit_checksum_ok(address)
    except (ValueError, KeyError):
        return False


# vbytes per input/output. "p2sh" inputs are nested P2SH-P2WPKH. This model
# reproduces the vsize of every fully readable row of the official sample.
INPUT_VBYTES = {"p2pkh": 148, "p2sh": 91, "p2wpkh": 68, "p2tr": 57.5}
OUTPUT_VBYTES = {"p2pkh": 34, "p2sh": 32, "p2wpkh": 31, "p2wsh": 43, "p2tr": 43}


def estimate_vsize(input_types: list[str], output_types: list[str]) -> int:
    overhead = 10 if all(t == "p2pkh" for t in input_types) else 10.5
    return math.ceil(overhead + sum(INPUT_VBYTES[t] for t in input_types)
                     + sum(OUTPUT_VBYTES[t] for t in output_types))


# =============================================================================
# GeoLite2 (Country CSV) sampling and lookup
# =============================================================================


class GeoLite:
    """Samples IPs from GeoLite2 country blocks and looks them up again."""

    def __init__(self, geolite_dir: Path, versions: tuple[int, ...], asn_csv: Path | None):
        self.iso_by_geoname: dict[str, str] = {}
        with open(geolite_dir / "GeoLite2-Country-Locations-en.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["country_iso_code"]:
                    self.iso_by_geoname[row["geoname_id"]] = row["country_iso_code"]
        # per version: sorted (start_int, end_int, iso)
        self.blocks: dict[int, list[tuple[int, int, str]]] = {}
        self.excluded: dict[str, int] = {}
        for v in versions:
            self.blocks[v] = self._load_blocks(geolite_dir / f"GeoLite2-Country-Blocks-IPv{v}.csv")
        self.starts = {v: [b[0] for b in bl] for v, bl in self.blocks.items()}
        self.by_country: dict[int, dict[str, list[int]]] = {}
        for v, bl in self.blocks.items():
            index: dict[str, list[int]] = {}
            for i, (_, _, iso) in enumerate(bl):
                index.setdefault(iso, []).append(i)
            self.by_country[v] = index
        self.asn = self._load_asn(asn_csv) if asn_csv else None

    def _load_blocks(self, path: Path) -> list[tuple[int, int, str]]:
        out = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                reason = None
                if not row["geoname_id"]:
                    reason = "no_country_geoname"
                elif row["geoname_id"] not in self.iso_by_geoname:
                    reason = "geoname_without_iso"
                elif "1" in (row["is_anonymous_proxy"], row["is_satellite_provider"],
                             row.get("is_anycast") or "0"):
                    reason = "proxy_satellite_or_anycast"
                if reason:
                    self.excluded[reason] = self.excluded.get(reason, 0) + 1
                    continue
                net = ipaddress.ip_network(row["network"])
                out.append((int(net.network_address), int(net.broadcast_address),
                            self.iso_by_geoname[row["geoname_id"]]))
        out.sort()
        return out

    @staticmethod
    def _load_asn(path: Path) -> dict[int, tuple[list[int], list[tuple[int, int, str]]]]:
        table: dict[int, list[tuple[int, int, str]]] = {}
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                net = ipaddress.ip_network(row["network"])
                table.setdefault(net.version, []).append(
                    (int(net.network_address), int(net.broadcast_address),
                     f'{row["autonomous_system_number"]}\t{row["autonomous_system_organization"]}'))
        return {v: ([r[0] for r in sorted(rows)], sorted(rows)) for v, rows in table.items()}

    @staticmethod
    def _find(starts: list[int], rows: list[tuple[int, int, str]], value: int) -> str | None:
        i = bisect.bisect_right(starts, value) - 1
        if i >= 0 and rows[i][0] <= value <= rows[i][1]:
            return rows[i][2]
        return None

    def country_of(self, ip: str) -> str | None:
        addr = ipaddress.ip_address(ip)
        if addr.version not in self.blocks:
            return None
        return self._find(self.starts[addr.version], self.blocks[addr.version], int(addr))

    def asn_of(self, ip: str) -> tuple[str, str]:
        if not self.asn:
            return "", ""
        addr = ipaddress.ip_address(ip)
        if addr.version not in self.asn:
            return "", ""
        starts, rows = self.asn[addr.version]
        hit = self._find(starts, rows, int(addr))
        return tuple(hit.split("\t", 1)) if hit else ("", "")  # type: ignore[return-value]

    def country_weights(self, version: int, mode: str) -> tuple[list[str], list[float]]:
        countries = sorted(self.by_country[version])
        if mode == "uniform":
            return countries, [1.0] * len(countries)
        rows = self.blocks[version]
        weights = [float(sum(rows[i][1] - rows[i][0] + 1 for i in self.by_country[version][c]))
                   for c in countries]
        return countries, weights

    def sample_ip(self, version: int, country: str, rng: random.Random) -> str:
        rows = self.blocks[version]
        candidates = self.by_country[version][country]
        for _ in range(200):
            start, end, _ = rows[rng.choice(candidates)]
            lo, hi = (start + 1, end - 1) if end - start >= 2 else (start, end)
            addr = ipaddress.ip_address(rng.randint(lo, hi))
            if addr.is_global and not addr.is_multicast:
                return str(addr)
        raise RuntimeError(f"could not sample a public IP in {country}")


# =============================================================================
# Simulation state
# =============================================================================


@dataclass
class Peer:
    ip: str
    country: str
    asn: str
    as_org: str
    user_agent: str


@dataclass
class Entity:
    entity_id: str
    entity_type: str  # user | merchant | exchange | illicit
    script_type: str
    home_peer: int | None
    addresses: list[str] = field(default_factory=list)
    utxos: set[str] = field(default_factory=set)

    @property
    def is_illicit(self) -> bool:
        return self.entity_type == "illicit"


@dataclass
class Utxo:
    outpoint: str
    address: str
    amount: int
    script_type: str
    owner: str | None       # entity id, None = external address
    created_at: datetime
    height: int             # confirmation height of the creating tx


@dataclass
class Meta:
    typology: str = "normal"
    instance_id: str = ""
    step: int = 0


class Simulator:
    def __init__(self, cfg: Config, geo: GeoLite):
        self.cfg = cfg
        self.geo = geo
        self.rng = random.Random(cfg.seed)
        self.t0 = datetime.fromisoformat(cfg.start_time.replace("Z", "+00:00"))
        self.t_end = self.t0 + timedelta(hours=cfg.hours)
        self.entities: dict[str, Entity] = {}
        self.by_type: dict[str, list[str]] = {}
        self.address_owner: dict[str, tuple[str | None, str]] = {}  # addr -> (entity, script type)
        self.utxos: dict[str, Utxo] = {}
        self.reserved: set[str] = set()
        self.rows: list[dict] = []
        self.tx_labels: list[dict] = []
        self.funding_addresses: dict[str, list[str]] = {}
        self.events: list = []
        self._seq = 0
        self.skipped: dict[str, int] = {}
        self.instances_started: dict[str, int] = {}
        self._blocks: list[datetime] = []
        self._chain_rng = random.Random(cfg.seed + 7)
        self._connections: dict[tuple[int, int], tuple[int, int]] = {}
        self._build_network()
        self._build_entities()

    # --- helpers --------------------------------------------------------------
    def _weighted(self, weights: dict[str, float]) -> str:
        keys = list(weights)
        return self.rng.choices(keys, [weights[k] for k in keys])[0]

    def _loguniform(self, lo: float, hi: float) -> int:
        return int(math.exp(self.rng.uniform(math.log(lo), math.log(hi))))

    def _exp(self, mean: float) -> timedelta:
        return timedelta(seconds=self.rng.expovariate(1.0 / mean))

    def _skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def schedule(self, when: datetime, fn: Callable, *args) -> None:
        self._seq += 1
        heapq.heappush(self.events, (when, self._seq, fn, args))

    # --- network ----------------------------------------------------------------
    def _new_peer(self) -> Peer:
        cfg = self.cfg
        version = 6 if self.rng.random() < cfg.ipv6_fraction else 4
        countries, weights = self._country_weights[version]
        country = self.rng.choices(countries, weights)[0]
        ip = self.geo.sample_ip(version, country, self.rng)
        asn, org = self.geo.asn_of(ip)
        return Peer(ip, country, asn, org, self.rng.choice(cfg.user_agents))

    def _build_network(self) -> None:
        versions = (4, 6) if self.cfg.ipv6_fraction > 0 else (4,)
        self._country_weights = {v: self.geo.country_weights(v, self.cfg.country_weighting)
                                  for v in versions}
        self.sensors = [self._new_peer() for _ in range(self.cfg.n_sensors)]
        self.peers = [self._new_peer() for _ in range(self.cfg.n_peers)]
        self.coordinator_peer = self.rng.randrange(len(self.peers))  # coinjoin coordinator

    def _connection(self, peer_i: int, sensor_i: int) -> tuple[int, int]:
        """Persistent connection -> (src_port, dst_port); src is always the peer."""
        key = (peer_i, sensor_i)
        if key not in self._connections:
            ephemeral = self.rng.randint(32768, 60999)
            if self.rng.random() < self.cfg.p_sensor_outbound:
                self._connections[key] = (8333, ephemeral)   # sensor dialled the peer
            else:
                self._connections[key] = (ephemeral, 8333)   # peer dialled the sensor
        return self._connections[key]

    # --- entities --------------------------------------------------------------
    def _build_entities(self) -> None:
        cfg = self.cfg
        counts = {"user": cfg.n_users, "merchant": cfg.n_merchants,
                  "exchange": cfg.n_exchanges, "illicit": cfg.n_illicit}
        for etype, n in counts.items():
            p_node = cfg.p_own_node_service if etype in ("merchant", "exchange") else cfg.p_own_node
            types = self._stratified_types(n)
            for i in range(n):
                eid = f"{etype}_{i:05d}"
                home = self.rng.randrange(len(self.peers)) if self.rng.random() < p_node else None
                ent = Entity(eid, etype, types[i], home)
                self.entities[eid] = ent
                self.by_type.setdefault(etype, []).append(eid)
                self._fund(ent)

    def _stratified_types(self, n: int) -> list[str]:
        """Script types in exact configured proportions (largest remainder),
        so small groups (e.g. 25 illicit actors) don't drift by chance."""
        w = self.cfg.script_type_weights
        total = sum(w.values())
        quotas = {k: n * v / total for k, v in w.items()}
        counts = {k: int(q) for k, q in quotas.items()}
        for k in sorted(quotas, key=lambda k: quotas[k] - counts[k], reverse=True)[: n - sum(counts.values())]:
            counts[k] += 1
        types = [k for k, c in counts.items() for _ in range(c)]
        self.rng.shuffle(types)
        return types

    def _fund(self, ent: Entity) -> None:
        """Genesis UTXOs: outputs of transactions that pre-date the dataset."""
        (cmin, cmax), (amin, amax) = self.cfg.funding[ent.entity_type]
        funded = []
        for _ in range(self.rng.randint(cmin, cmax)):
            addr = self.fresh_address(ent)
            op = f"{self.rng.randbytes(32).hex()}:{self.rng.randint(0, 3)}"
            self.utxos[op] = Utxo(op, addr, self._loguniform(amin, amax), ent.script_type,
                                  ent.entity_id, self.t0, self.cfg.start_block_height - 1)
            ent.utxos.add(op)
            funded.append(addr)
        self.funding_addresses[ent.entity_id] = funded

    def fresh_address(self, ent: Entity) -> str:
        addr = make_address(ent.script_type, self.rng)
        ent.addresses.append(addr)
        self.address_owner[addr] = (ent.entity_id, ent.script_type)
        return addr

    def receive_address(self, ent: Entity) -> str:
        if ent.addresses and self.rng.random() > self.cfg.p_fresh_receive_address:
            return self.rng.choice(ent.addresses)
        return self.fresh_address(ent)

    def external_output(self) -> tuple[str, str, None]:
        stype = self.rng.choice(self.cfg.external_script_types)
        addr = make_address(stype, self.rng)
        self.address_owner[addr] = (None, stype)
        return addr, stype, None

    def spendable(self, ent: Entity) -> list[str]:
        # sorted: set order depends on PYTHONHASHSEED, which would break reproducibility
        return sorted(u for u in ent.utxos if u not in self.reserved)

    def balance(self, ent: Entity) -> int:
        return sum(self.utxos[u].amount for u in self.spendable(ent))

    # --- chain -----------------------------------------------------------------
    def _extend_chain(self) -> None:
        """Append one block; whole-second timestamps, exponential spacing."""
        prev = self._blocks[-1] if self._blocks else self.t0
        gap = max(1, round(self._chain_rng.expovariate(1.0 / self.cfg.block_interval_s)))
        self._blocks.append(prev + timedelta(seconds=gap))

    def block_time(self, index: int) -> datetime:
        while len(self._blocks) <= index:
            self._extend_chain()
        return self._blocks[index]

    def first_block_after(self, t: datetime) -> int:
        """Index of the first block strictly after ``t``."""
        while not self._blocks or self._blocks[-1] <= t:
            self._extend_chain()
        return bisect.bisect_right(self._blocks, t)

    def tip_height(self, t: datetime) -> int:
        return self.cfg.start_block_height + self.first_block_after(t) - 1

    # --- transaction emission -------------------------------------------------------
    def emit(self, t: datetime, inputs: list[str], outputs: list[tuple[str, int, str, str | None]],
             meta: Meta, broadcaster: Entity | None) -> str:
        """Record one transaction. outputs = (address, amount, script_type, owner)."""
        cfg = self.cfg
        in_utxos = [self.utxos[op] for op in inputs]
        total_in = sum(u.amount for u in in_utxos)
        total_out = sum(o[1] for o in outputs)
        fee = total_in - total_out
        assert fee >= 0 and all(o[1] >= cfg.dust_limit for o in outputs), "invalid tx"
        vsize = estimate_vsize([u.script_type for u in in_utxos], [o[2] for o in outputs])
        version = 1 if self.rng.random() < cfg.p_version_1 else 2
        locktime = self.tip_height(t) if self.rng.random() < cfg.p_anti_fee_sniping else 0
        rbf = int(self.rng.random() < cfg.p_rbf)

        preimage = "|".join([str(version), *inputs, *(f"{a}:{v}" for a, v, _, _ in outputs),
                             str(locktime), self.rng.randbytes(8).hex()]).encode()
        txid = sha256d(preimage)[::-1].hex()  # display order, like real txids

        # confirmation: after observation, never before any parent's block
        idx = self.first_block_after(t)
        while self.rng.random() > cfg.p_confirm_next_block:
            idx += 1
        parent_height = max(u.height for u in in_utxos)
        height = max(cfg.start_block_height + idx, parent_height)
        block_t = self.block_time(height - cfg.start_block_height)

        for op in inputs:
            owner = self.utxos[op].owner
            if owner:
                self.entities[owner].utxos.discard(op)
            self.reserved.discard(op)
            del self.utxos[op]
        for vout, (addr, amount, stype, owner) in enumerate(outputs):
            op = f"{txid}:{vout}"
            self.utxos[op] = Utxo(op, addr, amount, stype, owner, t, height)
            if owner:
                self.entities[owner].utxos.add(op)

        spenders = {u.owner for u in in_utxos}
        receivers = {o[3] for o in outputs}
        illicit_spender = any(s and self.entities[s].is_illicit for s in spenders)
        self.tx_labels.append({
            "txid": txid,
            "label": "illicit" if illicit_spender else "licit",
            "typology": meta.typology,
            "instance_id": meta.instance_id,
            "step": meta.step,
            "spender_entities": "|".join(sorted(s for s in spenders if s)),
            "involves_illicit_output": int(any(r and self.entities[r].is_illicit for r in receivers)),
        })

        base = {
            "txid": txid, "block_height": height, "block_time": block_t, "is_coinbase": 0,
            "version": version, "locktime": locktime, "rbf": rbf,
            "input_count": len(inputs), "output_count": len(outputs),
            "input_prevouts": "|".join(inputs),
            "input_addresses": "|".join(u.address for u in in_utxos),
            "input_amounts": "|".join(str(u.amount) for u in in_utxos),
            "output_addresses": "|".join(o[0] for o in outputs),
            "output_amounts": "|".join(str(o[1]) for o in outputs),
            "output_script_types": "|".join(o[2] for o in outputs),
            "script_type": in_utxos[0].script_type,
            "total_input": total_in, "total_output": total_out, "fee": fee, "vsize": vsize,
            "fee_rate": f"{fee / vsize:.2f}",
        }
        peer_i = self._pick_broadcaster(broadcaster)
        self._observe(t, base, peer_i)
        seen_t = t
        while self.rng.random() < cfg.extra_observation_prob:
            seen_t += timedelta(milliseconds=self.rng.randint(50, 5000))
            self._observe(seen_t, base, self.rng.randrange(len(self.peers)))
        return txid

    def _pick_broadcaster(self, ent: Entity | None) -> int:
        if ent is not None and ent.home_peer is not None and self.rng.random() < self.cfg.p_use_own_node:
            return ent.home_peer
        return self.rng.randrange(len(self.peers))

    def _observe(self, t: datetime, base: dict, peer_i: int) -> None:
        sensor_i = self.rng.randrange(len(self.sensors))
        peer, sensor = self.peers[peer_i], self.sensors[sensor_i]
        src_port, dst_port = self._connection(peer_i, sensor_i)
        self.rows.append({
            "timestamp": t, "src_ip": peer.ip, "src_port": src_port,
            "dst_ip": sensor.ip, "dst_port": dst_port,
            "geo_country": peer.country, "asn": peer.asn, "as_org": peer.as_org,
            "peer_user_agent": peer.user_agent, **base,
        })

    # --- generic builders ----------------------------------------------------------
    def fee_rate(self) -> float:
        return self.rng.uniform(*self.cfg.fee_rate_range)

    def pay(self, t: datetime, ent: Entity, payments: list[tuple[str, int, str, str | None]],
            meta: Meta, inputs: list[str] | None = None, change_to: str | None = None) -> str | None:
        """Spend ``inputs`` (or coin-select) to ``payments`` plus change."""
        rate = self.fee_rate()
        target = sum(p[1] for p in payments)
        if inputs is None:
            pool = sorted(self.spendable(ent), key=lambda op: -self.utxos[op].amount)
            inputs = []
            for op in pool:
                inputs.append(op)
                need = target + math.ceil(rate * estimate_vsize(
                    [self.utxos[i].script_type for i in inputs],
                    [p[2] for p in payments] + [ent.script_type]))
                if sum(self.utxos[i].amount for i in inputs) >= need:
                    break
        if not inputs:
            return None
        total_in = sum(self.utxos[i].amount for i in inputs)
        in_types = [self.utxos[i].script_type for i in inputs]
        change_addr = change_to or self.fresh_address(ent)
        fee_with_change = math.ceil(rate * estimate_vsize(in_types, [p[2] for p in payments] + [ent.script_type]))
        change = total_in - target - fee_with_change
        outputs = list(payments)
        if change >= self.cfg.dust_limit:
            outputs.append((change_addr, change, ent.script_type, ent.entity_id))
        else:  # dust change is left to the fee, as wallets do
            fee_no_change = math.ceil(rate * estimate_vsize(in_types, [p[2] for p in payments]))
            if total_in - target < fee_no_change:
                return None
        return self.emit(t, inputs, outputs, meta, ent)

    def sweep(self, t: datetime, ent: Entity, inputs: list[str], to_addr: str, to_type: str,
              to_owner: str | None, meta: Meta) -> str | None:
        """Send the full value of ``inputs`` (minus fee) to one output."""
        total_in = sum(self.utxos[i].amount for i in inputs)
        fee = math.ceil(self.fee_rate() * estimate_vsize(
            [self.utxos[i].script_type for i in inputs], [to_type]))
        if total_in - fee < self.cfg.dust_limit:
            return None
        return self.emit(t, inputs, [(to_addr, total_in - fee, to_type, to_owner)], meta, ent)

    # --- licit behaviour --------------------------------------------------------------
    def recipient_output(self, sender: Entity, amount: int) -> tuple[str, int, str, str | None]:
        kind = self._weighted(self.cfg.recipient_weights)
        if kind == "external":
            addr, stype, owner = self.external_output()
            return addr, amount, stype, owner
        choices = [e for e in self.by_type[kind] if e != sender.entity_id]
        rec = self.entities[self.rng.choice(choices)]
        addr = self.fresh_address(rec) if kind == "exchange" else self.receive_address(rec)
        return addr, amount, rec.script_type, rec.entity_id

    def normal_payment(self, t: datetime) -> None:
        pool = self.by_type["user"] + self.by_type["merchant"]
        for _ in range(20):
            ent = self.entities[self.rng.choice(pool)]
            bal = self.balance(ent)
            amount = int(bal * self.rng.uniform(0.05, 0.6))
            if amount >= 10 * self.cfg.dust_limit:
                if self.pay(t, ent, [self.recipient_output(ent, amount)], Meta("payment")):
                    return
        self._skip("payment_no_funded_sender")

    def sweep_action(self, t: datetime) -> None:
        """Licit whole-coin moves: to a new own wallet address, or a full
        deposit at an exchange (1-in-1-out, or a few-in-1-out)."""
        pool = self.by_type["user"] + self.by_type["merchant"]
        for _ in range(20):
            ent = self.entities[self.rng.choice(pool)]
            utxos = self.spendable(ent)
            if not utxos:
                continue
            inputs = self.rng.sample(utxos, min(len(utxos), self.rng.choice((1, 1, 1, 2, 3))))
            if self.rng.random() < 0.5:
                addr, stype, owner = self.fresh_address(ent), ent.script_type, ent.entity_id
                meta = Meta("self_transfer")
            else:
                addr, stype, owner = self._exchange_deposit()
                meta = Meta("exchange_deposit")
            if self.sweep(t, ent, inputs, addr, stype, owner, meta):
                return
        self._skip("sweep_no_funded_entity")

    def exchange_batch(self, t: datetime) -> None:
        ex = self.entities[self.rng.choice(self.by_type["exchange"])]
        n = self.rng.randint(5, 30)
        users = self.rng.sample(self.by_type["user"], n)
        payments = []
        for uid in users:
            u = self.entities[uid]
            payments.append((self.receive_address(u), self._loguniform(100_000, 50_000_000),
                             u.script_type, uid))
        if not self.pay(t, ex, payments, Meta("exchange_batch_payout")):
            self._skip("exchange_batch_insufficient")

    def consolidation(self, t: datetime) -> None:
        eligible = [e for e in self.by_type["exchange"] + self.by_type["merchant"]
                    if len(self.spendable(self.entities[e])) >= 5]
        if not eligible:
            self._skip("consolidation_too_few_utxos")
            return
        ent = self.entities[self.rng.choice(eligible)]
        pool = self.spendable(ent)
        inputs = self.rng.sample(pool, min(len(pool), self.rng.randint(5, 40)))
        if not self.sweep(t, ent, inputs, self.fresh_address(ent), ent.script_type,
                          ent.entity_id, Meta("consolidation")):
            self._skip("consolidation_dust")

    def normal_tick(self, t: datetime) -> None:
        action = self._weighted(self.cfg.normal_action_weights)
        if action == "coinjoin":
            self.coinjoin(t, illicit=False)
        else:
            {"payment": self.normal_payment, "sweep": self.sweep_action,
             "exchange_batch": self.exchange_batch, "consolidation": self.consolidation}[action](t)
        nxt = t + self._exp(3600.0 / self.cfg.normal_tx_per_hour)
        if nxt < self.t_end:
            self.schedule(nxt, self.normal_tick)

    # --- coinjoin (licit or illicit) ---------------------------------------------------
    def coinjoin(self, t: datetime, illicit: bool, instance: str = "") -> None:
        cfg = self.cfg
        n = self.rng.randint(*cfg.coinjoin_participants)
        users = [e for e in self.by_type["user"] if self.entities[e].script_type == "p2wpkh"]
        picked = self.rng.sample(users, n - 1 if illicit else n)
        if illicit:
            actors = [e for e in self.by_type["illicit"] if self.entities[e].script_type == "p2wpkh"
                      and self.spendable(self.entities[e])]
            if not actors:
                self._skip("illicit_coinjoin_no_p2wpkh_actor")
                return
            picked.append(self.rng.choice(actors))
        contributions = []
        for eid in picked:
            ent = self.entities[eid]
            pool = self.spendable(ent)
            if pool:
                contributions.append((ent, max(pool, key=lambda op: self.utxos[op].amount)))
        if len(contributions) < 3:
            self._skip("coinjoin_too_few_participants")
            return
        rate = self.fee_rate()
        n_in = len(contributions)
        share = math.ceil(rate * estimate_vsize(["p2wpkh"] * n_in, ["p2wpkh"] * 2 * n_in) / n_in)
        smallest = min(self.utxos[op].amount for _, op in contributions) - share
        denoms = [d for d in cfg.coinjoin_denominations if d <= smallest]
        if not denoms:
            self._skip("coinjoin_inputs_too_small")
            return
        d = max(denoms)
        outputs = []
        for ent, op in contributions:
            outputs.append((self.fresh_address(ent), d, "p2wpkh", ent.entity_id))
            change = self.utxos[op].amount - d - share
            if change >= cfg.dust_limit:
                outputs.append((self.fresh_address(ent), change, "p2wpkh", ent.entity_id))
        self.rng.shuffle(outputs)
        meta = Meta("coinjoin", instance, 0)
        self.emit(t, [op for _, op in contributions], outputs, meta, self._coordinator_entity())

    def _coordinator_entity(self) -> Entity:
        # a pseudo-entity that always broadcasts via the coordinator's node
        return Entity("coordinator", "service", "p2wpkh", self.coordinator_peer)

    # --- illicit typologies --------------------------------------------------------------
    def _actor(self, min_balance: int = 0) -> Entity | None:
        funded = [e for e in self.by_type["illicit"] if self.balance(self.entities[e]) > min_balance]
        return self.entities[self.rng.choice(funded)] if funded else None

    def _reserve_largest(self, ent: Entity) -> str | None:
        pool = self.spendable(ent)
        if not pool:
            return None
        op = max(pool, key=lambda o: self.utxos[o].amount)
        self.reserved.add(op)
        return op

    def _exchange_deposit(self) -> tuple[str, str, str]:
        ex = self.entities[self.rng.choice(self.by_type["exchange"])]
        return self.fresh_address(ex), ex.script_type, ex.entity_id

    def start_instance(self, t: datetime, typology: str) -> None:
        self.instances_started[typology] = self.instances_started.get(typology, 0) + 1
        iid = f"{typology}_{self.instances_started[typology]:04d}"
        if typology == "illicit_coinjoin":
            self.coinjoin(t, illicit=True, instance=iid)
            return
        actor = self._actor(min_balance=1_000_000)
        if actor is None:
            self._skip(f"{typology}_no_funded_actor")
            return
        if typology == "ransomware":
            self.ransomware(t, actor, iid)
            return
        op = self._reserve_largest(actor)
        {"peeling_chain": self.peel_step, "fan_out_split": self.split,
         "rapid_layering": self.layer_hop, "circular": self.circular_start}[typology](t, actor, op, iid)

    def peel_step(self, t: datetime, actor: Entity, op: str, iid: str, step: int = 0,
                  steps: int | None = None) -> None:
        cfg = self.cfg
        steps = steps or self.rng.randint(*cfg.peel_steps)
        amount = self.utxos[op].amount
        peel = int(amount * self.rng.uniform(*cfg.peel_fraction))
        if peel < 10 * cfg.dust_limit:
            self.reserved.discard(op)
            return
        addr, stype, owner = self._exchange_deposit()  # peels are cashed out at exchanges
        change_addr = self.fresh_address(actor)
        txid = self.pay(t, actor, [(addr, peel, stype, owner)], Meta("peeling_chain", iid, step),
                        inputs=[op], change_to=change_addr)
        if txid is None:
            self.reserved.discard(op)
            return
        change_op = next((o for o in sorted(actor.utxos) if o.startswith(txid)), None)
        if change_op and step + 1 < steps:
            self.reserved.add(change_op)
            self.schedule(t + self._exp(cfg.peel_delay_mean_s), self.peel_step,
                          actor, change_op, iid, step + 1, steps)

    def split(self, t: datetime, actor: Entity, op: str, iid: str) -> None:
        cfg = self.cfg
        width = self.rng.randint(*cfg.split_width)
        total = self.utxos[op].amount
        fee = math.ceil(self.fee_rate() * estimate_vsize([actor.script_type], [actor.script_type] * width))
        part = (total - fee) // width
        if part < 20 * cfg.dust_limit:
            self.reserved.discard(op)
            return
        outputs = [(self.fresh_address(actor), part, actor.script_type, actor.entity_id)
                   for _ in range(width)]
        # the integer-division remainder is left to the fee
        txid = self.emit(t, [op], outputs, Meta("fan_out_split", iid, 0), actor)
        for vout in range(width):
            child = f"{txid}:{vout}"
            self.reserved.add(child)
            self.schedule(t + self._exp(cfg.split_forward_delay_mean_s), self.split_forward,
                          actor, child, iid)

    def split_forward(self, t: datetime, actor: Entity, op: str, iid: str) -> None:
        if self.rng.random() < 0.5:
            addr, stype, owner = self._exchange_deposit()
        else:
            addr, stype, owner = self.fresh_address(actor), actor.script_type, actor.entity_id
        if not self.sweep(t, actor, [op], addr, stype, owner, Meta("fan_out_split", iid, 1)):
            self.reserved.discard(op)

    def layer_hop(self, t: datetime, actor: Entity, op: str, iid: str, hop: int = 0,
                  hops: int | None = None) -> None:
        cfg = self.cfg
        hops = hops or self.rng.randint(*cfg.layering_hops)
        last = hop + 1 >= hops
        if last:
            addr, stype, owner = self._exchange_deposit()
        else:
            addr, stype, owner = self.fresh_address(actor), actor.script_type, actor.entity_id
        txid = self.sweep(t, actor, [op], addr, stype, owner, Meta("rapid_layering", iid, hop))
        if txid is None:
            self.reserved.discard(op)
            return
        if not last:
            nxt = f"{txid}:0"
            self.reserved.add(nxt)
            self.schedule(t + self._exp(cfg.layering_delay_mean_s), self.layer_hop,
                          actor, nxt, iid, hop + 1, hops)

    def circular_start(self, t: datetime, actor: Entity, op: str, iid: str) -> None:
        hops = self.rng.randint(*self.cfg.circular_hops)
        origin = self.utxos[op].address  # funds return here (address reuse)
        self.circular_hop(t, actor, op, iid, 0, hops, origin)

    def circular_hop(self, t: datetime, actor: Entity, op: str, iid: str, hop: int,
                     hops: int, origin: str) -> None:
        last = hop + 1 >= hops
        addr = origin if last else self.fresh_address(actor)
        txid = self.sweep(t, actor, [op], addr, actor.script_type, actor.entity_id,
                          Meta("circular", iid, hop))
        if txid is None:
            self.reserved.discard(op)
            return
        if not last:
            nxt = f"{txid}:0"
            self.reserved.add(nxt)
            self.schedule(t + self._exp(self.cfg.circular_delay_mean_s), self.circular_hop,
                          actor, nxt, iid, hop + 1, hops, origin)

    def ransomware(self, t: datetime, actor: Entity, iid: str) -> None:
        cfg = self.cfg
        # victims are users who can afford the maximum demand when the campaign starts
        able = [u for u in self.by_type["user"]
                if self.balance(self.entities[u]) >= cfg.ransom_amount[1] * 1.1]
        n = min(len(able), self.rng.randint(*cfg.ransom_victims))
        victims = self.rng.sample(able, n)
        collected: list[str] = []
        for i, vid in enumerate(victims):
            when = t + timedelta(seconds=self.rng.uniform(0, cfg.ransom_window_s))
            self.schedule(when, self.ransom_payment, self.entities[vid], actor, iid, i, collected)
        self.schedule(t + timedelta(seconds=cfg.ransom_window_s + 600), self.ransom_collect,
                      actor, iid, collected)

    def ransom_payment(self, t: datetime, victim: Entity, actor: Entity, iid: str, i: int,
                       collected: list[str]) -> None:
        amount = self.rng.randint(*self.cfg.ransom_amount)
        addr = self.fresh_address(actor)  # one fresh address per victim
        if self.balance(victim) < amount * 1.1:
            self._skip("ransom_victim_insufficient")
            return
        txid = self.pay(t, victim, [(addr, amount, actor.script_type, actor.entity_id)],
                        Meta("ransom_payment", iid, i))
        if txid:
            op = f"{txid}:0"  # payment is always output 0 in pay()
            self.reserved.add(op)
            collected.append(op)

    def ransom_collect(self, t: datetime, actor: Entity, iid: str, collected: list[str]) -> None:
        if len(collected) < 2:
            for op in collected:
                self.reserved.discard(op)
            self._skip("ransom_too_few_payments")
            return
        txid = self.sweep(t, actor, list(collected), self.fresh_address(actor), actor.script_type,
                          actor.entity_id, Meta("ransom_aggregation", iid, 0))
        if txid:
            op = f"{txid}:0"
            self.reserved.add(op)
            self.schedule(t + self._exp(self.cfg.peel_delay_mean_s), self.peel_step,
                          actor, op, iid + "_peel")

    # --- run ---------------------------------------------------------------------------
    def run(self) -> None:
        cfg = self.cfg
        self.schedule(self.t0 + self._exp(3600.0 / cfg.normal_tx_per_hour), self.normal_tick)
        span = (self.t_end - self.t0).total_seconds()
        for typology, per36h in cfg.typology_instances.items():
            for _ in range(max(1, round(per36h * cfg.hours / 36.0))):
                start = self.t0 + timedelta(seconds=self.rng.uniform(0, span * 0.85))
                self.schedule(start, self.start_instance, typology)
        while self.events:
            t, _, fn, args = heapq.heappop(self.events)
            t = t.replace(microsecond=(t.microsecond // 1000) * 1000)  # ms precision
            fn(t, *args)


# =============================================================================
# Output
# =============================================================================

COLUMNS = ["timestamp", "txid", "src_ip", "src_port", "dst_ip", "dst_port", "geo_country", "asn",
           "as_org", "peer_user_agent", "block_height", "block_time", "is_coinbase", "version",
           "locktime", "rbf", "input_count", "output_count", "input_prevouts", "input_addresses",
           "input_amounts", "output_addresses", "output_amounts", "output_script_types",
           "script_type", "total_input", "total_output", "fee", "vsize", "fee_rate"]


def iso_ms(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def write_outputs(sim: Simulator, out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = {name: out / f"{name}.csv" for name in (
        "btc_tx_traffic", "labels_transactions", "labels_addresses", "entities",
        "seed_illicit_addresses", "peers")}

    rows = sorted(sim.rows, key=lambda r: r["timestamp"])
    with open(paths["btc_tx_traffic"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r | {"timestamp": iso_ms(r["timestamp"]),
                            "block_time": r["block_time"].strftime("%Y-%m-%dT%H:%M:%S.000Z")})

    with open(paths["labels_transactions"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sim.tx_labels[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(sim.tx_labels)

    with open(paths["labels_addresses"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["address", "entity_id", "entity_type", "is_illicit", "script_type"])
        for addr, (eid, stype) in sim.address_owner.items():
            if eid is None:
                w.writerow([addr, "", "external", 0, stype])
            else:
                e = sim.entities[eid]
                w.writerow([addr, eid, e.entity_type, int(e.is_illicit), stype])

    with open(paths["entities"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["entity_id", "entity_type", "is_illicit", "script_type", "home_peer_ip",
                    "address_count"])
        for e in sim.entities.values():
            home = sim.peers[e.home_peer].ip if e.home_peer is not None else ""
            w.writerow([e.entity_id, e.entity_type, int(e.is_illicit), e.script_type, home,
                        len(e.addresses)])

    rng = random.Random(sim.cfg.seed + 1)
    known = [eid for eid in sim.by_type["illicit"] if rng.random() < sim.cfg.seed_fraction]
    with open(paths["seed_illicit_addresses"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["address", "entity_id", "source"])
        for eid in known:
            for addr in sim.funding_addresses[eid]:
                w.writerow([addr, eid, "known_funding_address"])

    with open(paths["peers"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ip", "role", "geo_country", "asn", "as_org", "user_agent"])
        for p in sim.sensors:
            w.writerow([p.ip, "sensor", p.country, p.asn, p.as_org, p.user_agent])
        for p in sim.peers:
            w.writerow([p.ip, "peer", p.country, p.asn, p.as_org, p.user_agent])
    return paths


# =============================================================================
# Independent verification (reads the written CSV back)
# =============================================================================


def verify(traffic: Path, geo: GeoLite, cfg: Config) -> dict[str, int]:
    """Re-check every invariant from the file on disk. Raises on any failure."""
    errors: list[str] = []
    counts = {"rows": 0, "checked_addresses": 0, "checked_ips": 0}
    outputs: dict[str, tuple[str, int, datetime, int]] = {}
    spent: set[str] = set()
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731

    with open(traffic, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen_tx: set[str] = set()
    for n, r in enumerate(rows, start=2):
        counts["rows"] += 1
        def fail(msg: str) -> None:
            errors.append(f"line {n}: {msg}")
        split = lambda k: r[k].split("|") if r[k] else []  # noqa: E731
        ins, in_amt = split("input_addresses"), [int(x) for x in split("input_amounts")]
        outs, out_amt = split("output_addresses"), [int(x) for x in split("output_amounts")]
        prevouts, out_types = split("input_prevouts"), split("output_script_types")
        ts, bt = parse(r["timestamp"]), parse(r["block_time"])

        if not (len(ins) == len(in_amt) == len(prevouts) == int(r["input_count"])):
            fail("input list lengths")
        if not (len(outs) == len(out_amt) == len(out_types) == int(r["output_count"])):
            fail("output list lengths")
        if sum(in_amt) != int(r["total_input"]) or sum(out_amt) != int(r["total_output"]):
            fail("totals")
        if int(r["total_input"]) - int(r["total_output"]) != int(r["fee"]):
            fail("fee")
        in_types = [r["script_type"]] * len(ins)
        if estimate_vsize(in_types, out_types) != int(r["vsize"]):
            fail("vsize")
        if f'{int(r["fee"]) / int(r["vsize"]):.2f}' != r["fee_rate"]:
            fail("fee_rate")
        if bt <= ts:
            fail("block_time not after observation")
        if any(a < cfg.dust_limit for a in out_amt):
            fail("dust output")
        for addr, st in zip(outs, out_types):
            counts["checked_addresses"] += 1
            if not address_is_valid(addr, st):
                fail(f"invalid {st} address")
        ip = r["src_ip"]
        counts["checked_ips"] += 2
        if geo.country_of(ip) != r["geo_country"]:
            fail("geo_country does not match GeoLite lookup of src_ip")
        for which in ("src_ip", "dst_ip"):
            if not ipaddress.ip_address(r[which]).is_global:
                fail(f"{which} not public")
        if not (0 < int(r["src_port"]) < 65536 and 0 < int(r["dst_port"]) < 65536):
            fail("port range")

        if r["txid"] in seen_tx:  # repeated observation of the same tx
            continue
        seen_tx.add(r["txid"])
        for op, addr, amt, st in zip(prevouts, ins, in_amt, in_types):
            if op in spent:
                fail(f"double spend of {op}")
            spent.add(op)
            if op in outputs:  # parent is in the dataset
                p_addr, p_amt, p_ts, p_height = outputs[op]
                if (p_addr, p_amt) != (addr, amt):
                    fail("prevout address/amount mismatch")
                if p_ts > ts or p_height > int(r["block_height"]):
                    fail("spends an output from the future")
        for vout, (addr, amt) in enumerate(zip(outs, out_amt)):
            outputs[f'{r["txid"]}:{vout}'] = (addr, amt, ts, int(r["block_height"]))
    if errors:
        raise AssertionError(f"{len(errors)} invariant violations, first: {errors[:5]}")
    counts["unique_txids"] = len(seen_tx)
    counts["in_dataset_parent_links"] = sum(1 for op in spent if op in outputs)
    return counts


def self_test() -> None:
    """Known-answer tests for the encoders and the vsize model."""
    assert base58check_encode(0x00, bytes(20)) == "1111111111111111111114oLvT2"
    assert segwit_encode("bc", 0, bytes.fromhex("751e76e8199196d454941c45d1b3a323f1433bd6")) \
        == "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"  # BIP-173 test vector
    official = [  # (input type, output types, vsize) from the official sample
        ("p2sh", ["p2pkh", "p2tr", "p2wpkh", "p2pkh"], 244),
        ("p2wpkh", ["p2sh", "p2wpkh"], 142),
        ("p2wpkh", ["p2wpkh", "p2wpkh"], 141),
        ("p2sh", ["p2wpkh", "p2wpkh"], 164),
        ("p2wpkh", ["p2sh", "p2tr", "p2pkh", "p2pkh", "p2wpkh"], 253),
    ]
    for i, o, v in official:
        assert estimate_vsize([i], o) == v, (i, o, v)


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic Bitcoin P2P traffic (PS-5 schema)")
    ap.add_argument("--geolite-dir", type=Path, required=True,
                    help="folder with GeoLite2-Country-Blocks-IPv4.csv and -Locations-en.csv")
    ap.add_argument("--asn-csv", type=Path, default=None,
                    help="optional GeoLite2-ASN-Blocks-IPv4.csv to fill asn/as_org")
    ap.add_argument("--out", type=Path, default=Path("dataset"))
    ap.add_argument("--seed", type=int, default=Config.seed)
    ap.add_argument("--hours", type=float, default=Config.hours)
    ap.add_argument("--ipv6-fraction", type=float, default=Config.ipv6_fraction)
    ap.add_argument("--extra-observation-prob", type=float, default=Config.extra_observation_prob)
    args = ap.parse_args()

    self_test()
    cfg = Config(seed=args.seed, hours=args.hours, ipv6_fraction=args.ipv6_fraction,
                 extra_observation_prob=args.extra_observation_prob)
    versions = (4, 6) if cfg.ipv6_fraction > 0 else (4,)
    print("Loading GeoLite2 ...")
    geo = GeoLite(args.geolite_dir, versions, args.asn_csv)

    print("Simulating ...")
    sim = Simulator(cfg, geo)
    sim.run()
    paths = write_outputs(sim, args.out)

    print("Verifying written file ...")
    checks = verify(paths["btc_tx_traffic"], geo, cfg)

    labels = sim.tx_labels
    typology_counts: dict[str, int] = {}
    for row in labels:
        typology_counts[row["typology"]] = typology_counts.get(row["typology"], 0) + 1
    meta = {
        "generator": "generate_btc_dataset.py",
        "config": asdict(cfg),
        "geolite": {
            "files": sorted(p.name for p in args.geolite_dir.glob("GeoLite2-*.csv")),
            "excluded_blocks": geo.excluded,
            "asn_source": str(args.asn_csv) if args.asn_csv else None,
            "attribution": "This product includes GeoLite2 data created by MaxMind, "
                           "available from https://www.maxmind.com.",
        },
        "counts": {
            "rows": len(sim.rows),
            "transactions": len(labels),
            "illicit_transactions": sum(1 for r in labels if r["label"] == "illicit"),
            "by_typology": dict(sorted(typology_counts.items())),
            "instances_started": sim.instances_started,
            "skipped_actions": sim.skipped,
            "entities": {k: len(v) for k, v in sim.by_type.items()},
            "sensors": [p.ip for p in sim.sensors],
        },
        "verification": checks,
    }
    (args.out / "generation_metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps(meta["counts"], indent=2))
    print(f"Verified {checks['rows']} rows: all invariants hold. Output in {args.out}/")


if __name__ == "__main__":
    main()
