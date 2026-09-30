"""IP address validation and classification.

Built on the standard library ``ipaddress`` module. Every IP is put into
exactly one category so downstream code never has to guess:

    invalid      -> could not be parsed
    unspecified  -> 0.0.0.0, ::
    loopback     -> 127.0.0.0/8, ::1
    link_local   -> 169.254.0.0/16, fe80::/10
    multicast    -> 224.0.0.0/4, ff00::/8
    private      -> 10/8, 172.16/12, 192.168/16, fc00::/7 (ULA), ...
    shared       -> 100.64.0.0/10 (carrier-grade NAT)
    documentation-> 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32
                    (common in synthetic data; never present in GeoLite)
    reserved     -> 240.0.0.0/4 and other IANA-reserved space
    special      -> anything else that is not globally routable
                    (documentation ranges, benchmarking, etc.)
    public       -> globally routable; the ONLY category we geolocate

IPv4-mapped IPv6 addresses (``::ffff:1.2.3.4``) are unwrapped to IPv4 first so
they are classified by the address they actually represent.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_DOCUMENTATION = tuple(
    ipaddress.ip_network(n)
    for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)


class IPCategory(str, Enum):
    INVALID = "invalid"
    UNSPECIFIED = "unspecified"
    LOOPBACK = "loopback"
    LINK_LOCAL = "link_local"
    MULTICAST = "multicast"
    PRIVATE = "private"
    SHARED = "shared"
    DOCUMENTATION = "documentation"
    RESERVED = "reserved"
    SPECIAL = "special"
    PUBLIC = "public"


@dataclass(frozen=True)
class IPInfo:
    raw: str | None
    normalized: str | None  # canonical text form, None if invalid
    version: int | None
    category: IPCategory

    @property
    def is_valid(self) -> bool:
        return self.category is not IPCategory.INVALID

    @property
    def is_public(self) -> bool:
        return self.category is IPCategory.PUBLIC


def parse_ip(value: object) -> IPAddress | None:
    """Parse a value into an IP address object, or ``None`` if malformed.

    Accepts surrounding whitespace and square brackets (``[2001:db8::1]``).
    Does NOT accept ``ip:port`` strings: ports are separate fields in the PS.
    IPv4 with leading zeros (``010.0.0.1``) is rejected by ``ipaddress``
    because it is ambiguous (octal vs decimal).
    """
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if not text:
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def categorize(address: IPAddress) -> IPCategory:
    """Assign exactly one category. Order matters: most specific first."""
    if address.is_unspecified:
        return IPCategory.UNSPECIFIED
    if address.is_loopback:
        return IPCategory.LOOPBACK
    if address.is_link_local:
        return IPCategory.LINK_LOCAL
    if address.is_multicast:
        return IPCategory.MULTICAST
    if isinstance(address, ipaddress.IPv4Address) and address in _CGNAT:
        return IPCategory.SHARED
    if any(address.version == net.version and address in net for net in _DOCUMENTATION):
        return IPCategory.DOCUMENTATION
    if address.is_reserved:
        return IPCategory.RESERVED
    if address.is_private:
        return IPCategory.PRIVATE
    if address.is_global:
        return IPCategory.PUBLIC
    return IPCategory.SPECIAL


@lru_cache(maxsize=500_000)
def classify_ip(value: str | None) -> IPInfo:
    """Validate and classify one IP string (cached: IPs repeat a lot)."""
    address = parse_ip(value)
    if address is None:
        return IPInfo(raw=value, normalized=None, version=None, category=IPCategory.INVALID)
    return IPInfo(
        raw=value,
        normalized=address.compressed,
        version=address.version,
        category=categorize(address),
    )


def is_valid_ip(value: str | None) -> bool:
    return classify_ip(value).is_valid


def is_geolocatable(value: str | None) -> bool:
    """True only for valid, globally routable addresses."""
    return classify_ip(value).is_public
