"""Essai d'un Candidat et son Aperçu, vus de l'extérieur de la stack.

L'essai cherche seul le Flux d'un Candidat sur les chemins courants des caméras, puis l'ouvre en
Aperçu : un chemin MediaMTX `apercu-<jeton>`, lu ici comme le Live le lirait. L'Aperçu devient une
Caméra par `POST /api/essai/camera`. Un seul essai pour le Site : chaque test retire le sien.
Sans renouvellement, l'Aperçu expire : délai raccourci pour les tests (tests/stack_compose.py).
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import pytest

from stack_compose import EXPIRATION_APERCU_S, URL_API, adresses_ip, compose, redemarrer_api, url_camera_simulee
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_connexion import se_connecter
from test_detection import ip_de
from test_etat_cameras import attendre_etat
from test_mediamtx_en_pont import attendre_lisible, lisible

# media/simulated/README.md
MOT_DE_PASSE_SIMULEE_2 = "argos-simulee"

# Un tour de réconciliation du pont, avec de la marge.
APRES_RECONCILIATION_S = 12
# Le retrait d'un Aperçu expiré passe au plus une seconde après l'échéance : large marge.
APRES_EXPIRATION_S = EXPIRATION_APERCU_S + 5
# Adresse privée du sous-réseau de simulation où aucun conteneur ne répond.
IP_SANS_CAMERA = "172.30.0.250"
# Sans réponse, l'essai attend la fin du délai de la sonde : large marge.
DELAI_ESSAI_S = 30


@pytest.fixture
def essai(connecte):
    """Ouvre l'essai d'une Caméra simulée ; l'essai et les Caméras ajoutées sont retirés à la fin."""
    ajoutees: list[int] = []

    def _essayer(numero: int, **champs) -> dict:
        reponse = connecte.post("/api/essai", json={"ip": ip_de(numero), "port": 554, **champs}, timeout=30)
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
        ("POST", "/api/essai/renouveler", None),
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


def test_camera_a_mot_de_passe_requis_puis_refuse_puis_trouve(essai):
    requis = essai(2)
    assert requis["issue"] == "identifiants_requis"
    assert requis["apercu"] is None

    refuse = essai(2, identifiant="admin", mot_de_passe="mauvais")
    assert refuse["issue"] == "identifiants_refuses"
    assert refuse["apercu"] is None

    trouve = essai(2, identifiant="admin", mot_de_passe=MOT_DE_PASSE_SIMULEE_2)
    assert trouve["issue"] == "flux_trouve"
    assert trouve["chemin"] == "/cam/realmonitor?channel=1&subtype=0"
    assert trouve["codec"] == "H264"
    attendre_lisible(trouve["apercu"], True)


def test_les_identifiants_ne_reviennent_jamais_au_navigateur(essai):
    resultat = essai(2, identifiant="admin", mot_de_passe=MOT_DE_PASSE_SIMULEE_2)

    assert MOT_DE_PASSE_SIMULEE_2 not in str(resultat)


def test_ajout_a_mot_de_passe_conserve_les_identifiants_et_masque_l_url(connecte, essai):
    essai(2, identifiant="admin", mot_de_passe=MOT_DE_PASSE_SIMULEE_2)

    reponse = essai.ajouter(nom=unique("Essai"))

    assert reponse.status_code == 201
    camera = reponse.json()
    assert camera["url_rtsp"] == f"rtsp://admin:***@{ip_de(2)}:554/cam/realmonitor?channel=1&subtype=0"
    assert MOT_DE_PASSE_SIMULEE_2 not in connecte.get(f"/api/cameras/{camera['id']}").text
    attendre_etat(connecte, camera["id"], "online")


def test_ajout_sans_essai_404(connecte):
    connecte.delete("/api/essai")

    assert connecte.post("/api/essai/camera", json={"nom": unique("Essai")}).status_code == 404


def test_flux_introuvable_puis_trouve_par_le_chemin_saisi(essai):
    introuvable = essai(3)
    assert introuvable["issue"] == "flux_introuvable"
    assert introuvable["apercu"] is None

    trouve = essai(3, chemin="/flux")

    assert trouve["issue"] == "flux_trouve"
    assert trouve["chemin"] == "/flux"
    assert trouve["codec"] == "H264"
    attendre_lisible(trouve["apercu"], True)


def test_un_nouvel_essai_retire_l_apercu_precedent(essai):
    premier = essai(1)["apercu"]
    attendre_lisible(premier, True)

    second = essai(1)["apercu"]

    assert second != premier
    assert not lisible(premier)
    assert lisible(second)


def test_sans_renouvellement_l_apercu_expire(connecte, essai):
    apercu = essai(1)["apercu"]

    time.sleep(APRES_EXPIRATION_S)

    assert not lisible(apercu)
    assert connecte.post("/api/essai/renouveler").status_code == 404
    assert connecte.post("/api/essai/camera", json={"nom": unique("Essai")}).status_code == 404


def test_le_renouvellement_prolonge_l_apercu(connecte, essai):
    apercu = essai(1)["apercu"]

    fin = time.monotonic() + APRES_EXPIRATION_S
    while time.monotonic() < fin:
        assert connecte.post("/api/essai/renouveler").status_code == 204
        time.sleep(EXPIRATION_APERCU_S / 4)

    assert lisible(apercu)


def test_renouveler_sans_essai_404(connecte):
    connecte.delete("/api/essai")

    assert connecte.post("/api/essai/renouveler").status_code == 404


def test_renouveler_un_essai_sans_flux_404(connecte, essai):
    assert essai(2)["issue"] == "identifiants_requis"

    assert connecte.post("/api/essai/renouveler").status_code == 404


def test_les_apercus_orphelins_sont_retires_au_demarrage_de_l_api(essai):
    apercu = essai(1)["apercu"]
    attendre_lisible(apercu, True)

    redemarrer_api()

    attendre_lisible(apercu, False)


def test_ip_privee_sans_camera_injoignable(connecte):
    reponse = connecte.post("/api/essai", json={"ip": IP_SANS_CAMERA}, timeout=DELAI_ESSAI_S)

    assert reponse.status_code == 200
    assert reponse.json()["issue"] == "injoignable"
    assert reponse.json()["apercu"] is None


def test_essai_simultane_409(administrateur):
    def essayer() -> httpx.Response:
        # Une session par appel : deux onglets.
        with httpx.Client(base_url=URL_API, timeout=DELAI_ESSAI_S) as client:
            assert se_connecter(client, **administrateur).status_code == 204
            return client.post("/api/essai", json={"ip": IP_SANS_CAMERA})

    with ThreadPoolExecutor(2) as appels:
        reponses = list(appels.map(lambda _: essayer(), range(2)))

    assert sorted(r.status_code for r in reponses) == [200, 409]
    refus = next(r for r in reponses if r.status_code == 409)
    assert "Un essai est déjà en cours" in refus.json()["detail"]


@pytest.mark.parametrize("ip", ["8.8.8.8", "100.64.0.1", "169.254.1.1", "127.0.0.1"])
def test_ip_hors_du_reseau_local_422(connecte, ip):
    reponse = connecte.post("/api/essai", json={"ip": ip})

    assert reponse.status_code == 422
    assert "réseau local" in reponse.json()["detail"]


@pytest.mark.parametrize("service", ["api", "mediamtx"])
def test_ip_d_argos_422(connecte, service):
    ip = next(ip for ip in adresses_ip(service) if ip.startswith("172.30."))

    reponse = connecte.post("/api/essai", json={"ip": ip}, timeout=DELAI_ESSAI_S)

    assert reponse.status_code == 422
    assert "ArgOS" in reponse.json()["detail"]


def test_journaux_une_ligne_par_essai_sans_identifiant(essai):
    depuis = datetime.now(UTC).isoformat()

    essai(2)
    essai(2, identifiant="admin", mot_de_passe=MOT_DE_PASSE_SIMULEE_2)

    journaux = compose("logs", "--no-log-prefix", "--since", depuis, "api").stdout
    requis, trouve = [ligne for ligne in journaux.splitlines() if "Essai :" in ligne]
    assert f" {ip_de(2)}:554 " in requis
    assert "identifiants_requis" in requis
    assert f" {ip_de(2)}:554 " in trouve
    assert "flux_trouve" in trouve
    assert "/cam/realmonitor?channel=1&subtype=0" in trouve
    assert "H264" in trouve
    assert MOT_DE_PASSE_SIMULEE_2 not in journaux
    assert "admin:" not in journaux
    assert "rtsp://" not in journaux


@pytest.mark.parametrize("active", [True, False])
def test_ip_deja_configuree_409_avec_la_camera(connecte, creer_camera, active):
    # Déclarée par son nom Compose : même rapprochement que la Détection, par IP résolue et port.
    camera = creer_camera(url_rtsp=url_camera_simulee(1, unique("essai"))).json()
    if not active:
        assert connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False}).status_code == 200
    connecte.delete("/api/essai")

    reponse = connecte.post("/api/essai", json={"ip": ip_de(1), "port": 554}, timeout=DELAI_ESSAI_S)

    assert reponse.status_code == 409
    assert reponse.json()["camera"] == {"id": camera["id"], "nom": camera["nom"]}
    assert reponse.json()["detail"] == f"Déjà configurée : {camera['nom']}"
    # Aucun essai ouvert : rien à renouveler.
    assert connecte.post("/api/essai/renouveler").status_code == 404
