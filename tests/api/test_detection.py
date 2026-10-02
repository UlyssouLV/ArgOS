"""Détection des Caméras, vue de l'extérieur de la stack.

La simulation ajoute son sous-réseau (172.30.0.0/24) à ceux de `.env` : la Détection y trouve les
trois Caméras simulées comme de vraies caméras. Seuls les Candidats de ce sous-réseau sont vérifiés,
`.env` pouvant autoriser aussi le réseau local de la machine.
"""

from ipaddress import ip_address, ip_network

import pytest

from stack_compose import adresses_ip
from test_cameras import connecte  # noqa: F401 (fixture)

SOUS_RESEAU_SIMULATION = "172.30.0.0/24"
# Un /24 sur deux ports tient en une dizaine de secondes : large marge.
DELAI_DETECTION_S = 60


@pytest.mark.parametrize("methode", ["GET", "POST"])
def test_detection_sans_session_401(client, methode):
    assert client.request(methode, "/api/detection").status_code == 401


def test_get_decrit_la_configuration(connecte):
    reponse = connecte.get("/api/detection")

    assert reponse.status_code == 200
    etat = reponse.json()
    assert etat["configuree"] is True
    assert etat["raison"] is None
    assert SOUS_RESEAU_SIMULATION in etat["sous_reseaux"]
    assert 554 in etat["ports"]


def test_post_trouve_les_trois_cameras_simulees_ni_la_base_ni_le_pont(connecte):
    cameras_simulees = {ip for n in (1, 2, 3) for ip in adresses_ip(f"camera-simulee-{n}")}
    argos = adresses_ip("db") | adresses_ip("mediamtx") | adresses_ip("api")

    reponse = connecte.post("/api/detection", timeout=DELAI_DETECTION_S)

    assert reponse.status_code == 200
    resultat = reponse.json()
    assert SOUS_RESEAU_SIMULATION in resultat["sous_reseaux"]
    assert 554 in resultat["ports"]
    assert resultat["duree_s"] >= 0
    candidats = [(c["ip"], c["port"]) for c in resultat["candidats"]]
    assert candidats == sorted(candidats, key=lambda c: (ip_address(c[0]), c[1]))
    simulation = {
        (ip, port) for ip, port in candidats if ip_address(ip) in ip_network(SOUS_RESEAU_SIMULATION)
    }
    # Ni la base, ni le pont, ni l'hôte qui publie le pont (passerelle du réseau de simulation).
    assert simulation == {(ip, 554) for ip in cameras_simulees}
    assert not argos & {ip for ip, _ in candidats}
