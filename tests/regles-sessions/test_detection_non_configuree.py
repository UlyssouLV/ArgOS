"""Réglage de la Détection vide ou invalide : l'API démarre, seule la Détection est indisponible, avec la raison."""

import pytest
from fastapi.testclient import TestClient

from argos_api.app import creer_app
from argos_api.configuration import Configuration
from conftest import IDENTIFIANT, MOT_DE_PASSE, se_connecter


def test_reglage_vide_detection_non_configuree_le_reste_marche(url_base, horloge):
    configuration = Configuration(
        ARGOS_IDENTIFIANT=IDENTIFIANT,
        ARGOS_MOT_DE_PASSE=MOT_DE_PASSE,
        ARGOS_URL_BASE=url_base,
        ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX="",
    )
    client = TestClient(creer_app(configuration, horloge))
    assert se_connecter(client).status_code == 204

    etat = client.get("/api/detection")
    detection = client.post("/api/detection")

    assert etat.status_code == 200
    assert etat.json() | {"raison": None} == {
        "configuree": False,
        "sous_reseaux": [],
        "ports": [554, 8554],
        "raison": None,
    }
    assert "non configurée" in etat.json()["raison"]
    assert detection.status_code == 409
    assert detection.json()["detail"] == etat.json()["raison"]
    # Administration et Live lisent les Caméras : intactes.
    assert client.get("/api/cameras").status_code == 200


@pytest.mark.parametrize(
    ("sous_reseaux", "ports", "dans_la_raison"),
    [
        # 2048 adresses : au-delà du plafond.
        ("10.0.0.0/21", "554", "plafond de 1024"),
        # 1024 + 4 adresses au total.
        ("10.0.0.0/23,10.1.0.0/23,10.2.0.0/30", "554", "plafond de 1024"),
        ("192.168.1.300/24", "554", "192.168.1.300/24"),
        ("192.168.1.0/24", "554,rtsp", "rtsp"),
    ],
)
def test_reglage_invalide_detection_refusee_avec_la_raison_le_reste_marche(
    url_base, horloge, sous_reseaux, ports, dans_la_raison
):
    configuration = Configuration(
        ARGOS_IDENTIFIANT=IDENTIFIANT,
        ARGOS_MOT_DE_PASSE=MOT_DE_PASSE,
        ARGOS_URL_BASE=url_base,
        ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX=sous_reseaux,
        ARGOS_DETECTION_CAMERAS_PORTS=ports,
    )
    client = TestClient(creer_app(configuration, horloge))
    assert se_connecter(client).status_code == 204

    etat = client.get("/api/detection")
    detection = client.post("/api/detection")

    assert etat.status_code == 200
    assert etat.json()["configuree"] is False
    assert "invalide" in etat.json()["raison"]
    assert dans_la_raison in etat.json()["raison"]
    assert detection.status_code == 409
    assert detection.json()["detail"] == etat.json()["raison"]
    assert client.get("/api/cameras").status_code == 200


def test_plafond_atteint_sans_le_depasser_detection_configuree(url_base, horloge):
    configuration = Configuration(
        ARGOS_IDENTIFIANT=IDENTIFIANT,
        ARGOS_MOT_DE_PASSE=MOT_DE_PASSE,
        ARGOS_URL_BASE=url_base,
        # 1024 adresses ; le doublon ne compte qu'une fois.
        ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX="10.0.0.0/23,10.1.0.0/23,10.1.0.0/23",
    )
    client = TestClient(creer_app(configuration, horloge))
    assert se_connecter(client).status_code == 204

    assert client.get("/api/detection").json()["configuree"] is True
