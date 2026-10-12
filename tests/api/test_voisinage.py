"""Module de voisinage : normalisation de la MAC et lecture d'une table de voisinage (tests unitaires).

Seuls tests qui lisent une table de voisinage : ailleurs, la MAC se vérifie par la réponse HTTP.
"""

from ipaddress import IPv4Address

import pytest

from argos_api import voisinage

# Format de /proc/net/arp : en-tête, puis une ligne par voisin. Flags 0x2 : entrée complète.
TABLE = """\
IP address       HW type     Flags       HW address            Mask     Device
172.30.0.11      0x1         0x2         02:a6:05:00:00:01     *        eth1
172.30.0.12      0x1         0x0         00:00:00:00:00:00     *        eth1
172.30.0.13      0x1         0x6         02:A6:05:00:00:03     *        eth1
192.168.1.20     0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0
"""


@pytest.mark.parametrize(
    "saisie",
    [
        "aa:bb:cc:dd:ee:ff",
        "AA:BB:CC:DD:EE:FF",
        "aa-bb-cc-dd-ee-ff",
        "AA-BB-CC-DD-EE-FF",
        "aabb.ccdd.eeff",
        "AABBCCDDEEFF",
        "  Aa:bB:cC:Dd:eE:Ff  ",
    ],
)
def test_normaliser_accepte_les_formats_d_etiquette(saisie):
    assert voisinage.normaliser(saisie) == "aa:bb:cc:dd:ee:ff"


@pytest.mark.parametrize(
    "saisie",
    [
        "",
        "aa:bb:cc:dd:ee",
        "aa:bb:cc:dd:ee:ff:00",
        "gg:bb:cc:dd:ee:ff",
        "aa:bb:cc:dd:ee:f",
        "aa bb cc dd ee ff",
        "aa:bb-cc:dd:ee:ff:",
    ],
)
def test_normaliser_refuse_une_saisie_invalide(saisie):
    with pytest.raises(ValueError):
        voisinage.normaliser(saisie)


@pytest.fixture
def table(tmp_path):
    chemin = tmp_path / "arp"
    chemin.write_text(TABLE)
    return chemin


def test_mac_de_lit_une_entree_complete(table):
    assert voisinage.mac_de(IPv4Address("172.30.0.11"), table) == "02:a6:05:00:00:01"
    assert voisinage.mac_de(IPv4Address("192.168.1.20"), table) == "aa:bb:cc:dd:ee:ff"


def test_mac_de_normalise_la_mac_lue(table):
    assert voisinage.mac_de(IPv4Address("172.30.0.13"), table) == "02:a6:05:00:00:03"


def test_mac_de_ignore_une_entree_incomplete(table):
    assert voisinage.mac_de(IPv4Address("172.30.0.12"), table) is None


def test_mac_de_ip_absente(table):
    assert voisinage.mac_de(IPv4Address("172.30.0.99"), table) is None


def test_mac_de_sans_table(tmp_path):
    assert voisinage.mac_de(IPv4Address("172.30.0.11"), tmp_path / "absente") is None
