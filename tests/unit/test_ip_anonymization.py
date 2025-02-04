"""Test anonymization of IP addresses and related functions."""
#   Copyright 2018 Intentionet
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from __future__ import unicode_literals

import ipaddress
import re

import pytest

from netconan.ip_anonymization import (
    IpAnonymizer,
    IpV6Anonymizer,
    _ensure_unicode,
    anonymize_ip_addr,
)

ip_v4_classes = [
    "0.0.0.0/1",  # Class A
    "128.0.0.0/2",  # Class B
    "192.0.0.0/3",  # Class C
    "224.0.0.0/4",  # Class D (implies class E)
]

ip_v4_list = [
    ("12.13.14.15"),
    ("237.73.212.5"),
    ("123.45.67.89"),
    ("92.210.0.255"),
    ("128.7.55.12"),
    ("223.123.21.99"),
    ("193.99.99.99"),
    ("225.99.99.99"),
    ("241.99.99.99"),
    ("249.99.99.99"),
    ("254.254.254.254"),
    ("009.010.011.012"),
    ("1.2.3.0000014"),
]

ip_v6_list = [
    ("1234::5678"),
    ("::1"),
    ("1::"),
    ("1::1"),
    ("2001:db8:85a3:7:8:8a2e:370:7334"),
    ("2001:db8:a0b:12f0::1"),
    ("ffff:ffff::ffff:ffff"),
    ("a:b:c:d:e:f:1:2"),
    ("aAaA:bBbB:cCcC:dDdD:eEeE:fFfF:1010:2929"),
    ("ffff:eeee:dddd:cccc:bbbb:AaAa:9999:8888"),
]

# Private-use blocks defined at https://www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml
# Tuples consist of: start of block, end of block, block subnet
private_blocks = [
    ("10.0.0.0", "10.255.255.255", "10.0.0.0/8"),
    ("172.16.0.0", "172.31.255.255", "172.16.0.0/12"),
    ("192.168.0.0", "192.168.255.255", "192.168.0.0/16"),
]

SALT = "saltForTest"


@pytest.fixture(scope="module")
def anonymizer_v4():
    """Most tests in this module use a single IPv4 anonymizer."""
    return IpAnonymizer(SALT)


@pytest.fixture(scope="module")
def anonymizer_v6():
    """All tests in this module use a single IPv6 anonymizer."""
    return IpV6Anonymizer(SALT)


@pytest.fixture(scope="module")
def anonymizer(request):
    """Create a generic fixture for different types of anonymizers."""
    if request.param == "v4":
        return IpAnonymizer(SALT)
    elif request.param == "v6":
        return IpV6Anonymizer(SALT)
    elif request.param == "flipv4":
        return IpAnonymizer(SALT, salter=lambda a, b: 1)
    else:
        raise ValueError("Invalid anonymizer type {}".format(request.param))


@pytest.fixture(scope="module")
def flip_anonymizer_v4():
    """Create an anonymizer that flips every bit except for class bits."""
    # Don't preserve private blocks, because that reduces the number of bits flipped
    return IpAnonymizer(SALT, preserve_prefixes=ip_v4_classes, salter=lambda a, b: 1)


def anonymize_line_general(anonymizer, line, ip_addrs):
    """Test IP address removal from config lines."""
    line_w_ip = line.format(*ip_addrs)
    anon_line = anonymize_ip_addr(anonymizer, line_w_ip)

    # Now anonymize each IP address individually & build another anonymized line
    anon_ip_addrs = [anonymize_ip_addr(anonymizer, ip_addr) for ip_addr in ip_addrs]
    individually_anon_line = line.format(*anon_ip_addrs)

    # Make sure anonymizing each address individually is the same as
    # anonymizing all at once
    assert anon_line == individually_anon_line

    for ip_addr in ip_addrs:
        # Make sure the original ip address(es) are removed from the anonymized line
        assert ip_addr not in anon_line


@pytest.mark.parametrize(
    "line, ip_addrs",
    [
        ("ip address {} 255.255.255.254", ["123.45.67.89"]),
        ("ip address {} 255.0.0.0", ["10.0.0.0"]),
        ("ip address {}/16", ["10.0.0.0"]),
        ("tacacs-server host {}", ["10.1.1.17"]),
        ("tacacs-server host {}", ["001.021.201.012"]),
        ("syscon address {} Password", ["10.73.212.5"]),
        ("1 permit tcp host {} host {} eq 2", ["1.2.3.4", "1.2.3.45"]),
        ("1 permit tcp host {} host {} eq 2", ["1.2.123.4", "11.2.123.4"]),
        ("1 permit tcp host {} host {} eq 2", ["1.2.30.45", "1.2.30.4"]),
        ("1 permit tcp host {} host {} eq 2", ["11.20.3.4", "1.20.3.4"]),
        ("something host {} host {} host {}", ["1.2.3.4", "1.2.3.5", "1.2.3.45"]),
        # These formats may occur in Batfish output
        ('"{}"', ["1.2.3.45"]),
        ("({})", ["1.2.3.45"]),
        ("[IP addresses:{},{}]", ["1.2.3.45", "1.2.3.5"]),
        ("flow:{}->{}", ["1.2.3.45", "1.2.3.5"]),
        ("something={}", ["1.2.3.45"]),
        ("something <{}>", ["1.2.3.45"]),
        ("something '{}'", ["1.2.3.45"]),
    ],
)
def test_v4_anonymize_line(anonymizer_v4, line, ip_addrs):
    """Test IPv4 address removal from config lines."""
    anonymize_line_general(anonymizer_v4, line, ip_addrs)


@pytest.mark.parametrize("enclosing", "_:;[]$~!@#$%^&*()-+=[]|<>?")
def test_v4_anonymize_enclosed_addr(anonymizer_v4, enclosing):
    """Test IPv4 address removal from config lines with different enclosing characters."""
    ip_addr = "1.2.3.4"
    line = enclosing + "{}" + enclosing
    anonymize_line_general(anonymizer_v4, line, [ip_addr])


@pytest.mark.parametrize(
    "line, ip_addrs",
    [
        ("ip address {} something::something", ["1234::5678"]),
        ("ip address {} blah {}", ["1234::", "1234:5678::9abc:def0"]),
        ("ip address {} blah {} blah", ["::1", "1234:5678:abcd:dcba::9abc:def0"]),
        ("ip address {}/16 blah", ["::1"]),
        ("ip address {}/16 blah", ["1::"]),
        ("ip address {}/16 blah", ["1::1"]),
        ("ip address {}/16 blah", ["ffff:ffff::ffff:ffff"]),
    ],
)
def test_v6_anonymize_line(anonymizer_v6, line, ip_addrs):
    """Test IPv6 address removal from config lines."""
    anonymize_line_general(anonymizer_v6, line, ip_addrs)


@pytest.mark.parametrize("enclosing", ".;[]$~!@#$%^&*()-+=[]|<>?")
def test_v6_anonymize_enclosed_addr(anonymizer_v6, enclosing):
    """Test IPv6 address removal from config lines with different enclosing characters."""
    ip_addr = "1::1"
    line = enclosing + "{}" + enclosing
    anonymize_line_general(anonymizer_v6, line, [ip_addr])


def get_ip_v4_class(ip_int):
    """Return the letter corresponding to the IP class the ip_int is in."""
    if (ip_int & 0x80000000) == 0x00000000:
        return "A"
    elif (ip_int & 0xC0000000) == 0x80000000:
        return "B"
    elif (ip_int & 0xE0000000) == 0xC0000000:
        return "C"
    elif (ip_int & 0xF0000000) == 0xE0000000:
        return "D"
    else:
        return "E"


def get_ip_v4_class_mask(ip_int):
    """Return a mask indicating bits preserved when preserving class."""
    if (ip_int & 0xE0000000) == 0xE0000000:
        return 0xF0000000
    elif (ip_int & 0xC0000000) == 0xC0000000:
        return 0xE0000000
    elif (ip_int & 0x80000000) == 0x80000000:
        return 0xC0000000
    else:
        return 0x80000000


@pytest.mark.parametrize(
    "ip_addr",
    [
        "0.0.0.0",
        "127.255.255.255",  # Class A
        "128.0.0.0",
        "191.255.255.255",  # Class B
        "192.0.0.0",
        "223.255.255.255",  # Class C
        "224.0.0.0",
        "239.255.255.255",  # Class D
        "240.0.0.0",
        "247.255.255.255",  # Class E
    ],
)
def test_v4_class_preserved(flip_anonymizer_v4, ip_addr):
    """Test that IPv4 classes are preserved."""
    ip_int = int(flip_anonymizer_v4.make_addr(ip_addr))
    ip_int_anon = flip_anonymizer_v4.anonymize(ip_int)

    # IP v4 class should match after anonymization
    assert get_ip_v4_class(ip_int) == get_ip_v4_class(ip_int_anon)

    # Anonymized ip address should not match the original ip address
    assert ip_int != ip_int_anon

    # All bits that are not forced to be preserved are flipped
    class_mask = get_ip_v4_class_mask(ip_int)
    assert 0xFFFFFFFF ^ class_mask == ip_int ^ ip_int_anon


def test_preserve_custom_prefixes():
    """Test that a custom prefix is preserved correctly."""
    subnet = "170.0.0.0/8"
    anonymizer = IpAnonymizer(SALT, [subnet])

    ip_start = int(anonymizer.make_addr("170.0.0.0"))
    ip_start_anon = anonymizer.anonymize(ip_start)

    ip_end = int(anonymizer.make_addr("170.255.255.255"))
    ip_end_anon = anonymizer.anonymize(ip_end)

    network = ipaddress.ip_network(_ensure_unicode(subnet))

    # Make sure the anonymized addresses are different from the originals
    assert ip_start_anon != ip_start
    assert ip_end_anon != ip_end

    # Make sure the anonymized addresses have the same prefix as the originals
    assert ipaddress.ip_address(ip_start_anon) in network
    assert ipaddress.ip_address(ip_end_anon) in network


def test_preserve_custom_addresses():
    """Test that addresses within a preserved block are flagged correctly as NOT needing anonymization."""
    addresses = [
        "170.0.0.0/8",
        "11.11.11.11",
    ]
    anonymizer = IpAnonymizer(SALT, preserve_addresses=addresses)

    ip_start = int(anonymizer.make_addr("170.0.0.0"))
    ip_end = int(anonymizer.make_addr("170.255.255.255"))
    ip_other = int(anonymizer.make_addr("11.11.11.11"))
    ip_outside = int(anonymizer.make_addr("10.11.12.13"))

    # Make sure anonymizer indicates addresses within preserved network blocks should not be anonymized
    assert not anonymizer.should_anonymize(ip_start)
    assert not anonymizer.should_anonymize(ip_end)
    assert not anonymizer.should_anonymize(ip_other)

    # Make sure the address outside the preserved block should be anonymized
    assert anonymizer.should_anonymize(ip_outside)


def test_preserve_address_preserves_prefix():
    """Test that common prefixes are still preserved when addresses are preserved."""
    addr_str = "11.11.11.11"
    addr = ipaddress.ip_address(addr_str)
    addr_int = int(addr)

    anonymizer = IpAnonymizer(SALT, preserve_addresses=[addr_str])

    addr_len = addr.max_prefixlen
    for i in range(addr_len):
        # Anonymize an address similar to the original, with 1 bit flipped
        similar_addr = ipaddress.ip_address(addr_int ^ (1 << i))
        similar_anon = ipaddress.ip_address(anonymizer.anonymize(int(similar_addr)))
        # Confirm cpl before anonymization matches cpl after anonymization
        assert _cpl_v4(similar_anon, addr) == _cpl_v4(similar_addr, addr)


def _cpl_v4(left, right):
    """
    Return the common prefix length for two IPv4 addresses.

    e.g.
    _cpl_v4(1.0.0.1, 1.0.0.1) == 32
    _cpl_v4(1.0.0.1, 1.0.128.1) == 16
    _cpl_v4(1.0.0.1, 128.0.0.1) == 0
    """
    xor = int(left) ^ int(right)
    max_shift = 32
    for i in reversed(range(max_shift)):
        if xor & (0x1 << i):
            return max_shift - 1 - i
    return max_shift


@pytest.mark.parametrize("start, end, subnet", private_blocks)
def test_preserve_private_prefixes(anonymizer_v4, start, end, subnet):
    """Test that private-use prefixes are preserved by default."""
    ip_int_start = int(anonymizer_v4.make_addr(start))
    ip_int_start_anon = anonymizer_v4.anonymize(ip_int_start)

    ip_int_end = int(anonymizer_v4.make_addr(end))
    ip_int_end_anon = anonymizer_v4.anonymize(ip_int_end)

    network = ipaddress.ip_network(_ensure_unicode(subnet))

    # Make sure addresses in the block stay in the block
    assert ipaddress.ip_address(ip_int_start_anon) in network
    assert ipaddress.ip_address(ip_int_end_anon) in network


@pytest.mark.parametrize("length", range(0, 33))
def test_preserve_host_bits(length):
    """Test that host bits are preserved, for every length."""
    anonymizer = IpAnonymizer(
        salt=SALT, salter=lambda a, b: 1, preserve_suffix=length, preserve_prefixes=[]
    )
    anonymized = anonymizer.anonymize(0)

    # The first <32-length> bits are 1, the last <length> bits are all 0
    expected = "1" * (32 - length) + "0" * length
    assert "{:032b}".format(anonymized) == expected

    # Deanonymization flips the bits back
    deanonymized = anonymizer.deanonymize(anonymized)
    assert deanonymized == 0


@pytest.mark.parametrize(
    "anonymizer,ip_addr",
    [("v4", s) for s in ip_v4_list] + [("v6", s) for s in ip_v6_list],
    indirect=["anonymizer"],
)
def test_anonymize_addr(anonymizer, ip_addr):
    """Test conversion from original to anonymized IP address."""
    ip_int = int(anonymizer.make_addr(ip_addr))
    ip_int_anon = anonymizer.anonymize(ip_int)

    # Anonymized ip address should not match the original address
    assert ip_int != ip_int_anon

    full_bit_mask = (1 << anonymizer.length) - 1

    # Confirm prefixes for similar addresses are preserved after anonymization
    for i in range(0, anonymizer.length):
        # Flip the ith bit of the org address and use that as the similar address
        diff_mask = 1 << i
        ip_int_similar = ip_int ^ diff_mask
        ip_int_similar_anon = anonymizer.anonymize(ip_int_similar)

        # Using i + 1 since same_mask should mask off ith bit, not preserve it
        same_mask = full_bit_mask & (full_bit_mask << (i + 1))

        # Common prefix for addresses should match after anonymization
        assert ip_int_similar_anon & same_mask == ip_int_anon & same_mask

        # Confirm the bit that is different in the original addresses is different in the anonymized addresses
        assert ip_int_similar_anon & diff_mask != ip_int_anon & diff_mask


def test_anonymize_ip_order_independent():
    """Test to make sure order does not affect anonymization of addresses."""
    anonymizer_v4_forward = IpAnonymizer(SALT)
    ip_lookup_forward = {}
    for ip_addr in ip_v4_list:
        ip_int = int(anonymizer_v4_forward.make_addr(ip_addr))
        ip_int_anon = anonymizer_v4_forward.anonymize(ip_int)
        ip_lookup_forward[ip_int] = ip_int_anon

    anonymizer_v4_reverse = IpAnonymizer(SALT)
    for ip_addr in reversed(ip_v4_list):
        ip_int_reverse = int(anonymizer_v4_reverse.make_addr(ip_addr))
        ip_int_anon_reverse = anonymizer_v4_reverse.anonymize(ip_int_reverse)
        # Confirm anonymizing in reverse order does not affect
        # anonymization results
        assert ip_int_anon_reverse == ip_lookup_forward[ip_int_reverse]

    anonymizer_v4_extras = IpAnonymizer(SALT)
    for ip_addr in ip_v4_list:
        ip_int_extras = int(anonymizer_v4_extras.make_addr(ip_addr))
        ip_int_anon_extras = anonymizer_v4_extras.anonymize(ip_int_extras)
        ip_int_inverted = ip_int_extras ^ 0xFFFFFFFF
        anonymizer_v4_extras.anonymize(ip_int_inverted)
        # Confirm anonymizing with extra addresses in-between does not
        # affect anonymization results
        assert ip_int_anon_extras == ip_lookup_forward[ip_int_extras]


@pytest.mark.parametrize("ip_addr", ip_v4_list)
def test_deanonymize_ip(anonymizer_v4, ip_addr):
    """Test reversing IP anonymization."""
    ip_int = int(anonymizer_v4.make_addr(ip_addr))
    ip_int_anon = anonymizer_v4.anonymize(ip_int)
    ip_int_unanon = anonymizer_v4.deanonymize(ip_int_anon)

    # Make sure unanonymizing an anonymized address produces the original address
    assert ip_int == ip_int_unanon


def test_dump_iptree(tmpdir, anonymizer_v4):
    """Test ability to accurately dump IP address anonymization mapping."""
    ip_mapping = {}
    ip_mapping_from_dump = {}

    # Make sure all addresses to be checked are in ip_tree and generate reference mapping
    for ip_addr_raw in ip_v4_list:
        ip_addr = anonymizer_v4.make_addr(ip_addr_raw)
        ip_int = int(ip_addr)
        ip_int_anon = anonymizer_v4.anonymize(ip_int)
        ip_addr_anon = str(ipaddress.IPv4Address(ip_int_anon))
        ip_mapping[str(ip_addr)] = ip_addr_anon

    filename = str(tmpdir.mkdir("test").join("test_dump_iptree.txt"))
    with open(filename, "w") as f_tmp:
        anonymizer_v4.dump_to_file(f_tmp)

    with open(filename, "r") as f_tmp:
        # Build mapping dict from the output of the ip_tree dump
        for line in f_tmp.readlines():
            m = re.match(r"\s*(\d+\.\d+.\d+.\d+)\s+(\d+\.\d+.\d+.\d+)\s*", line)
            ip_addr = m.group(1)
            ip_addr_anon = m.group(2)
            ip_mapping_from_dump[ip_addr] = ip_addr_anon

    for ip_addr in ip_mapping:
        # Confirm anon addresses from ip_tree dump match anon addresses from _convert_to_anon_ip
        assert ip_mapping[ip_addr] == ip_mapping_from_dump[ip_addr]


@pytest.mark.parametrize(
    "line",
    [
        "01:23:45:67:89:ab",
        "01:02:03:04:05:06:07:08:09",
        "01:02:03:04::05:06:07:08",
        "1.2.3.4.example.net",
        "1.2.3.4something.example.net",
        "a.1.2.3.4",
        "1.2.3",
        "1.2.3.4.5",
        "something1::abc",
        "123::ABsomething",
        "1.2.333.4",
        "1.2.0333.4",
        "1.256.3.4",
    ],
)
def test_false_positives(anonymizer_v4, anonymizer_v6, line):
    """Test that text without a valid address is not anonymized."""
    anon_line = anonymize_ip_addr(anonymizer_v4, line)
    anon_line = anonymize_ip_addr(anonymizer_v6, anon_line)

    # Confirm the anonymized line is unchanged
    assert line == anon_line


@pytest.mark.parametrize(
    "zeros, no_zeros",
    [
        ("0.0.0.0", "0.0.0.0"),
        ("0.0.0.3", "0.0.0.3"),
        ("128.0.0.0", "128.0.0.0"),
        ("0.127.0.0", "0.127.0.0"),
        ("10.73.212.5", "10.73.212.5"),
        ("010.73.212.05", "10.73.212.5"),
        ("255.255.255.255", "255.255.255.255"),
        ("170.255.85.1", "170.255.85.1"),
        ("10.11.12.13", "10.11.12.13"),
        ("010.11.12.13", "10.11.12.13"),
        ("10.011.12.13", "10.11.12.13"),
        ("10.11.012.13", "10.11.12.13"),
        ("10.11.12.013", "10.11.12.13"),
        ("010.0011.00000012.000", "10.11.12.0"),
    ],
)
def test_v4_anonymizer_ignores_leading_zeros(anonymizer_v4, zeros, no_zeros):
    """Test that v4 IP address ignore leading zeros & don't interpret octal."""
    assert ipaddress.IPv4Address(no_zeros) == anonymizer_v4.make_addr(zeros)


@pytest.mark.parametrize(
    "ip_int, expected",
    [
        (0b00000000000000000000000000000000, False),
        (0b00000000000000000000000000000001, False),
        (0b00000000000000000000000000001111, False),
        (0b11110000000000000000000000000000, False),
        (0b10000000000000000000000000000000, False),
        (0b01111111111000000000000000000000, True),
        (0b00000011111000000000000000000000, True),
        (0b00000000000100000000000000000000, True),
        (0b00010101001001000000000000000000, True),
        (0b00000000000000000010000000000000, True),
        (0b00000000000000000011111111111110, True),
        (0b00000000010000000100000000000000, True),
    ],
)
def test_v4_should_anonymize(anonymizer_v4, ip_int, expected):
    """Test that the IpV4 anonymizer does not anonymize masks."""
    assert expected == anonymizer_v4.should_anonymize(ip_int)
