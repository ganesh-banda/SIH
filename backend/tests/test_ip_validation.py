import pytest

from app.preprocessing.ip_validation import IPCategory, classify_ip, is_geolocatable, parse_ip


@pytest.mark.parametrize("ip, category", [
    ("8.8.8.8", IPCategory.PUBLIC),
    ("2606:4700:4700::1111", IPCategory.PUBLIC),
    ("10.0.0.1", IPCategory.PRIVATE),
    ("10.255.255.255", IPCategory.PRIVATE),
    ("172.16.0.1", IPCategory.PRIVATE),
    ("172.31.255.255", IPCategory.PRIVATE),
    ("172.32.0.1", IPCategory.PUBLIC),          # just outside 172.16/12
    ("172.15.255.255", IPCategory.PUBLIC),      # just below 172.16/12
    ("192.168.1.1", IPCategory.PRIVATE),
    ("127.0.0.1", IPCategory.LOOPBACK),
    ("127.8.9.10", IPCategory.LOOPBACK),
    ("::1", IPCategory.LOOPBACK),
    ("fc00::1", IPCategory.PRIVATE),            # IPv6 ULA
    ("fd12:3456::1", IPCategory.PRIVATE),
    ("fe80::1", IPCategory.LINK_LOCAL),
    ("169.254.1.1", IPCategory.LINK_LOCAL),
    ("224.0.0.1", IPCategory.MULTICAST),
    ("ff02::1", IPCategory.MULTICAST),
    ("0.0.0.0", IPCategory.UNSPECIFIED),
    ("::", IPCategory.UNSPECIFIED),
    ("100.64.0.1", IPCategory.SHARED),
    ("240.0.0.1", IPCategory.RESERVED),
    ("203.0.113.7", IPCategory.DOCUMENTATION),
    ("198.51.100.1", IPCategory.DOCUMENTATION),
    ("2001:db8::1", IPCategory.DOCUMENTATION),
])
def test_categories(ip, category):
    assert classify_ip(ip).category is category


@pytest.mark.parametrize("bad", ["", "   ", "abc", "256.1.1.1", "1.2.3", "1.2.3.4.5",
                                 "1.2.3.4:8333", "010.0.0.1", "gggg::1", None])
def test_malformed_ips_are_invalid(bad):
    info = classify_ip(bad)
    assert info.category is IPCategory.INVALID
    assert info.normalized is None
    assert not info.is_valid


def test_whitespace_and_brackets_are_accepted():
    assert classify_ip("  8.8.8.8 ").normalized == "8.8.8.8"
    assert classify_ip("[2606:4700::1111]").normalized == "2606:4700::1111"


def test_ipv6_is_compressed():
    assert classify_ip("2606:4700:0000:0000:0000:0000:0000:1111").normalized == "2606:4700::1111"


def test_ipv4_mapped_ipv6_is_unwrapped():
    assert classify_ip("::ffff:8.8.8.8").normalized == "8.8.8.8"
    assert classify_ip("::ffff:10.0.0.1").category is IPCategory.PRIVATE


def test_only_public_is_geolocatable():
    assert is_geolocatable("8.8.8.8")
    assert not is_geolocatable("192.168.0.1")
    assert not is_geolocatable("203.0.113.1")
    assert not is_geolocatable("nonsense")


def test_parse_ip_rejects_bool():
    assert parse_ip(True) is None
