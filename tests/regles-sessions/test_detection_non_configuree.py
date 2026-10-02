"""Réglage de la Détection vide : l'API démarre, seule la Détection est indisponible, avec la raison."""

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
