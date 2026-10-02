"""Détection des Caméras, vue de l'extérieur de la stack.

La simulation ajoute son sous-réseau (172.30.0.0/24) à ceux de `.env` : la Détection y trouve les
trois Caméras simulées comme de vraies caméras. Seuls les Candidats de ce sous-réseau sont vérifiés,
`.env` pouvant autoriser aussi le réseau local de la machine.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network

import httpx
import pytest

from stack_compose import URL_API, adresses_ip, compose, url_camera_simulee
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_connexion import se_connecter

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


def candidats_simules(resultat: dict) -> dict[str, dict]:
    """Candidats du sous-réseau de simulation sur le port 554, par IP."""
    return {
        c["ip"]: c
        for c in resultat["candidats"]
        if ip_address(c["ip"]) in ip_network(SOUS_RESEAU_SIMULATION) and c["port"] == 554
    }


def ip_de(numero: int) -> str:
    (ip,) = adresses_ip(f"camera-simulee-{numero}")
    return ip


def deja_declarees(connecte, numero: int) -> list[dict]:
    """Caméras du Site (même hors test) déclarées sur une Caméra simulée, par son nom ou son IP, port 554."""
    hotes = {f"camera-simulee-{numero}", ip_de(numero)}
    return [c for c in connecte.get("/api/cameras").json() if c["hote"] in hotes and c["port"] == 554]


def correspondance(connecte, numero: int) -> dict | None:
    """Plusieurs Caméras sur la même IP et le même port : la plus ancienne."""
    cameras = sorted(deja_declarees(connecte, numero), key=lambda c: c["id"])
    return {"id": cameras[0]["id"], "nom": cameras[0]["nom"]} if cameras else None


def test_candidat_deja_configure_porte_sa_camera_active_ou_desactivee(connecte, creer_camera):
    # camera-simulee-1 déclarée par son nom Compose, active ; camera-simulee-2 désactivée.
    assert creer_camera(url_rtsp=url_camera_simulee(1, "flux", unique("detection"))).status_code == 201
    desactivee = creer_camera(url_rtsp=url_camera_simulee(2, "flux", unique("detection"))).json()
    assert connecte.patch(f"/api/cameras/{desactivee['id']}", json={"active": False}).status_code == 200
    attendues = {ip_de(n): correspondance(connecte, n) for n in (1, 2, 3)}

    reponse = connecte.post("/api/detection", timeout=DELAI_DETECTION_S)

    assert reponse.status_code == 200
    simules = candidats_simules(reponse.json())
    assert {ip: c["camera"] for ip, c in simules.items()} == attendues
    assert attendues[ip_de(1)] is not None
    assert attendues[ip_de(2)] is not None


def test_candidats_portent_statut_rtsp_et_serveur(connecte):
    reponse = connecte.post("/api/detection", timeout=DELAI_DETECTION_S)

    assert reponse.status_code == 200
    simules = candidats_simules(reponse.json())
    assert len(simules) == 3
    for candidat in simules.values():
        # Caméras simulées : MediaMTX répond 200 à OPTIONS, même celle à identifiant.
        assert candidat["statut_rtsp"] == 200
        assert candidat["serveur"] == "gortsplib"


def test_seconde_detection_simultanee_409(administrateur):
    def detecter() -> httpx.Response:
        # Une session par appel : deux Administrateurs, deux onglets.
        with httpx.Client(base_url=URL_API, timeout=DELAI_DETECTION_S) as client:
            assert se_connecter(client, **administrateur).status_code == 204
            return client.post("/api/detection")

    with ThreadPoolExecutor(2) as appels:
        reponses = list(appels.map(lambda _: detecter(), range(2)))

    assert sorted(r.status_code for r in reponses) == [200, 409]
    refus = next(r for r in reponses if r.status_code == 409)
    assert "déjà en cours" in refus.json()["detail"]


def test_journaux_une_ligne_par_candidat_et_un_bilan(connecte):
    depuis = datetime.now(UTC).isoformat()

    reponse = connecte.post("/api/detection", timeout=DELAI_DETECTION_S)

    assert reponse.status_code == 200
    resultat = reponse.json()
    journaux = compose("logs", "--no-log-prefix", "--since", depuis, "api").stdout.splitlines()
    lignes_candidats = [ligne for ligne in journaux if "Détection : Candidat" in ligne]
    assert len(lignes_candidats) == len(resultat["candidats"])
    for ip in (ip_de(n) for n in (1, 2, 3)):
        (ligne,) = [ligne for ligne in lignes_candidats if f" {ip}:554 " in ligne]
        assert "RTSP 200" in ligne
        assert "Server gortsplib" in ligne
    (bilan,) = [ligne for ligne in journaux if "Détection : bilan" in ligne]
    assert SOUS_RESEAU_SIMULATION in bilan
    assert "554" in bilan
    assert f"{len(resultat['candidats'])} Candidat(s)" in bilan
