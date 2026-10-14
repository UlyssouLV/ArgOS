"""Réseau des caméras (macvlan, prod Linux) : une sortie seulement pour l'API (ADR 0003).

macvlan n'existe pas sous Docker Desktop : l'adresse locale d'arrivée d'une requête est simulée par
l'hôte de l'URL du client de test (le serveur ASGI la reçoit comme adresse locale de la connexion).
"""

import socket
import threading
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from argos_api import soi
from argos_api.app import creer_app
from argos_api.configuration import Configuration
from conftest import IDENTIFIANT, MOT_DE_PASSE, URL_SITE, se_connecter

# Adresse d'ArgOS sur le réseau des caméras (plages de documentation : jamais jointe).
IP_ARGOS = "192.0.2.250"


def demarrer(url_base, horloge, **reglages: str) -> FastAPI:
    return creer_app(
        Configuration(
            ARGOS_IDENTIFIANT=IDENTIFIANT,
            ARGOS_MOT_DE_PASSE=MOT_DE_PASSE,
            ARGOS_URL_BASE=url_base,
            **reglages,
        ),
        horloge,
    )


@pytest.mark.parametrize("chemin", ["/api/docs", "/api/instance", "/api/moi", "/api/cameras"])
def test_requete_arrivee_sur_l_adresse_du_reseau_des_cameras_refusee(url_base, horloge, chemin):
    app = demarrer(url_base, horloge, ARGOS_RESEAU_CAMERAS_ADRESSES=IP_ARGOS)
    depuis_les_cameras = TestClient(app, base_url=f"http://{IP_ARGOS}:8000")

    reponse = depuis_les_cameras.get(chemin)

    assert reponse.status_code == 403
    assert "réseau des caméras" in reponse.text


def test_connexion_refusee_sur_l_adresse_du_reseau_des_cameras(url_base, horloge):
    app = demarrer(url_base, horloge, ARGOS_RESEAU_CAMERAS_ADRESSES=IP_ARGOS)
    depuis_les_cameras = TestClient(app, base_url=f"http://{IP_ARGOS}:8000")

    reponse = se_connecter(depuis_les_cameras)

    assert reponse.status_code == 403
    assert "set-cookie" not in reponse.headers


@pytest.mark.parametrize("hote", ["localhost:8000", "127.0.0.1:8000", "172.18.0.4:8000"], ids=["healthcheck", "boucle", "bridge"])
def test_healthcheck_et_bridge_restent_servis(url_base, horloge, hote):
    app = demarrer(url_base, horloge, ARGOS_RESEAU_CAMERAS_ADRESSES=IP_ARGOS)
    client = TestClient(app, base_url=f"http://{hote}")

    assert client.get("/api/docs").status_code == 200
    assert se_connecter(client).status_code == 204


@pytest.fixture
def camera_locale() -> Iterator[int]:
    """Un hôte qui répond en RTSP sur 127.0.0.1 : un Candidat, à moins d'être ArgOS."""
    serveur = socket.create_server(("127.0.0.1", 0))
    serveur.settimeout(0.2)
    arret = threading.Event()

    def repondre() -> None:
        while not arret.is_set():
            try:
                connexion, _ = serveur.accept()
            except TimeoutError:
                continue
            with connexion:
                connexion.recv(4096)
                connexion.sendall(b"RTSP/1.0 200 OK\r\nCSeq: 1\r\n\r\n")

    fil = threading.Thread(target=repondre, daemon=True)
    fil.start()
    yield serveur.getsockname()[1]
    arret.set()
    fil.join()
    serveur.close()


@pytest.mark.parametrize(("adresses_argos", "candidats"), [("", ["127.0.0.1"]), ("127.0.0.1", [])], ids=["camera", "argos"])
def test_ip_d_argos_sur_le_reseau_des_cameras_jamais_candidat(
    url_base, horloge, camera_locale, monkeypatch, adresses_argos, candidats
):
    # Hors conteneur, le nom de la machine se résout en 127.0.0.1 : seule l'adresse configurée doit l'écarter.
    monkeypatch.setattr(soi, "adresses_des_conteneurs", lambda hotes: set())
    app = demarrer(
        url_base,
        horloge,
        ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX="127.0.0.1/32",
        ARGOS_DETECTION_CAMERAS_PORTS=str(camera_locale),
        ARGOS_RESEAU_CAMERAS_ADRESSES=adresses_argos,
    )
    client = TestClient(app, base_url=URL_SITE)
    assert se_connecter(client).status_code == 204

    detection = client.post("/api/detection")

    assert detection.status_code == 200, detection.text
    assert [c["ip"] for c in detection.json()["candidats"]] == candidats
