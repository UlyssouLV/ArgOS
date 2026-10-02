"""Essai d'un Candidat et son Aperçu, vus de l'extérieur de la stack.

L'essai cherche seul le Flux d'un Candidat sur les chemins courants des caméras, puis l'ouvre en
Aperçu : un chemin MediaMTX `apercu-<jeton>`, lu ici comme le Live le lirait. L'Aperçu devient une
Caméra par `POST /api/essai/camera`. Un seul essai pour le Site : chaque test retire le sien.
"""

import time

import pytest

from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_detection import ip_de
from test_etat_cameras import attendre_etat
from test_mediamtx_en_pont import attendre_lisible, lisible

# Un tour de réconciliation du pont, avec de la marge.
APRES_RECONCILIATION_S = 12


@pytest.fixture
def essai(connecte):
    """Ouvre l'essai d'une Caméra simulée ; l'essai et les Caméras ajoutées sont retirés à la fin."""
    ajoutees: list[int] = []

    def _essayer(numero: int) -> dict:
        reponse = connecte.post("/api/essai", json={"ip": ip_de(numero), "port": 554}, timeout=30)
        assert reponse.status_code == 200
        return reponse.json()

    def _ajouter(**champs):
        reponse = connecte.post("/api/essai/camera", json=champs)
        if reponse.status_code == 201:
            ajoutees.append(reponse.json()["id"])
        return reponse

    _essayer.ajouter = _ajouter
    yield _essayer

    connecte.delete("/api/essai")
    for id_camera in ajoutees:
        if connecte.patch(f"/api/cameras/{id_camera}", json={"active": False}).status_code == 200:
            assert connecte.delete(f"/api/cameras/{id_camera}").status_code == 204


@pytest.mark.parametrize(
    ("methode", "chemin", "corps"),
    [
        ("POST", "/api/essai", {"ip": "172.30.0.2", "port": 554}),
        ("DELETE", "/api/essai", None),
        ("POST", "/api/essai/camera", {"nom": "Entrée"}),
    ],
)
def test_essai_sans_session_401(client, methode, chemin, corps):
    assert client.request(methode, chemin, json=corps).status_code == 401


def test_essai_trouve_le_chemin_hikvision_et_ouvre_l_apercu(essai):
    resultat = essai(1)

    assert resultat["issue"] == "flux_trouve"
    assert resultat["chemin"] == "/Streaming/Channels/101"
    assert resultat["codec"] == "H264"
    assert resultat["apercu"].startswith("apercu-")
    attendre_lisible(resultat["apercu"], True)


def test_delete_retire_l_apercu(connecte, essai):
    apercu = essai(1)["apercu"]
    attendre_lisible(apercu, True)

    assert connecte.delete("/api/essai").status_code == 204

    assert not lisible(apercu)
    # Idempotent.
    assert connecte.delete("/api/essai").status_code == 204


def test_l_apercu_survit_a_la_reconciliation_du_pont(essai):
    apercu = essai(1)["apercu"]

    time.sleep(APRES_RECONCILIATION_S)

    assert lisible(apercu)


def test_ajout_cree_une_camera_active_qui_passe_online_et_retire_l_apercu(connecte, essai):
    apercu = essai(1)["apercu"]
    nom = unique("Essai")

    reponse = essai.ajouter(nom=nom, emplacement="Portail")

    assert reponse.status_code == 201
    camera = reponse.json()
    assert camera["nom"] == nom
    assert camera["emplacement"] == "Portail"
    assert camera["active"] is True
    assert camera["hote"] == ip_de(1)
    assert camera["port"] == 554
    assert camera["url_rtsp"] == f"rtsp://{ip_de(1)}:554/Streaming/Channels/101"
    assert not lisible(apercu)
    attendre_etat(connecte, camera["id"], "online")


def test_ajout_d_un_nom_pris_409_et_l_essai_reste_ouvert(essai, creer_camera):
    pris = creer_camera().json()["nom"]
    apercu = essai(1)["apercu"]

    reponse = essai.ajouter(nom=pris)

    assert reponse.status_code == 409
    assert reponse.json()["detail"] == "Une Caméra porte déjà ce nom ou cette URL (désactivée comprise)."
    assert lisible(apercu)
    assert essai.ajouter(nom=unique("Essai")).status_code == 201


def test_ajout_sans_essai_404(connecte):
    connecte.delete("/api/essai")

    assert connecte.post("/api/essai/camera", json={"nom": unique("Essai")}).status_code == 404
