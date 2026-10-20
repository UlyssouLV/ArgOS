"""Serveur de temps du Site vu de l'API (tests unitaires) : source transmise à `temps`, état lu en NTP, adresse
annoncée aux Caméras.

`temps` est remplacé par un faux serveur NTP local qui répond une strate et un identifiant de référence choisis ;
le vrai `temps` est joué de bout en bout dans `test_heure_du_site.py`.
"""

import socket
import struct
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from argos_api import serveur_de_temps

EPOQUE_NTP = 2_208_988_800


@pytest.fixture
def faux_temps() -> Iterator:
    """Démarre un faux serveur NTP sur 127.0.0.1 ; renvoie son port. Il répond `octet_0`, `strate`, `reference`."""
    prises: list[socket.socket] = []

    def _demarrer(strate: int, reference: bytes = b"\x00" * 4, octet_0: int = 0x24) -> int:
        prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        prise.bind(("127.0.0.1", 0))
        prises.append(prise)

        def repondre() -> None:
            try:
                _, client = prise.recvfrom(512)
            except OSError:
                return
            maintenant = time.time() + EPOQUE_NTP
            emission = struct.pack("!II", int(maintenant), int((maintenant % 1) * 2**32))
            prise.sendto(bytes([octet_0, strate]) + bytes(10) + reference + bytes(24) + emission, client)

        threading.Thread(target=repondre, daemon=True).start()
        return prise.getsockname()[1]

    yield _demarrer
    for prise in prises:
        prise.close()


def test_temps_qui_suit_sa_source_dit_laquelle_et_son_heure(faux_temps):
    port = faux_temps(strate=3, reference=socket.inet_aton("162.159.200.1"))

    etat = serveur_de_temps.interroger("127.0.0.1", port)

    assert etat.source_utilisee == "ntp"
    assert etat.reference == "162.159.200.1"
    assert abs((etat.heure - datetime.now(UTC)).total_seconds()) < 1


def test_temps_en_strate_10_sert_l_horloge_du_serveur(faux_temps):
    etat = serveur_de_temps.interroger("127.0.0.1", faux_temps(strate=10, reference=b"\x7f\x7f\x01\x01"))

    assert (etat.source_utilisee, etat.reference) == ("horloge_serveur", None)
    assert etat.heure is not None


def test_temps_pas_encore_synchronise(faux_temps):
    # Indicateur de seconde intercalaire 3 : horloge non synchronisée.
    etat = serveur_de_temps.interroger("127.0.0.1", faux_temps(strate=0, octet_0=0xE4))

    assert etat.source_utilisee == "non_synchronise"


def test_temps_muet_injoignable():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as muet:
        muet.bind(("127.0.0.1", 0))

        etat = serveur_de_temps.interroger("127.0.0.1", muet.getsockname()[1], delai_s=0.2)

    assert (etat.source_utilisee, etat.reference, etat.heure) == ("injoignable", None, None)


def test_temps_introuvable_injoignable():
    assert serveur_de_temps.interroger("temps.invalid", delai_s=0.2).source_utilisee == "injoignable"


@pytest.mark.parametrize(
    ("serveur", "ligne"),
    [("pool.ntp.org", "pool.ntp.org\n"), ("192.168.1.1", "192.168.1.1\n"), (None, "\n")],
)
def test_source_transmise_par_le_fichier_du_volume_partage(tmp_path, serveur, ligne):
    serveur_de_temps.transmettre(tmp_path, serveur)

    assert (tmp_path / "source").read_text() == ligne
    # Rien d'autre dans le dossier : le fichier temporaire est renommé.
    assert [chemin.name for chemin in tmp_path.iterdir()] == ["source"]


@pytest.mark.parametrize(
    ("ip_temps", "ips_du_site", "annoncee"),
    [
        # IP fixe de temps sur le réseau des caméras (macvlan), sinon l'IP du Site.
        ("192.168.1.3", "192.168.1.20", "192.168.1.3"),
        ("", "192.168.1.20,10.0.0.5", "192.168.1.20"),
        # Un nom (pas une IP) ou une IP invalide ne s'annonce pas.
        ("", "argos.local,192.168.1.20", "192.168.1.20"),
        ("pas-une-ip", "192.168.1.20", "192.168.1.20"),
        ("", "", None),
        ("", "argos.local", None),
    ],
)
def test_adresse_annoncee_aux_cameras(ip_temps, ips_du_site, annoncee):
    assert serveur_de_temps.adresse_annoncee(ip_temps, ips_du_site) == annoncee
