"""Autre Appareil à l'adresse d'une Caméra, vu par la surveillance, de l'extérieur de la stack.

Les Caméras simulées ne servent chacune qu'un chemin : l'autre Appareil est une Caméra simulée rattachée à
la même IP avec une autre MAC (stack_compose.deplacer_cameras_simulees), qui sert donc le même Flux. Chaque
test remet les Caméras simulées à leur adresse et leur MAC d'origine.
"""

import time

import httpx
import pytest

from stack_compose import IPS_SIMULEES, MACS_SIMULEES, deplacer_cameras_simulees, remettre_cameras_simulees, url_camera_simulee
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_essai import essai  # noqa: F401 (fixture)
from test_mediamtx_en_pont import attendre_lisible
from test_suivi_adresse import DELAI_VOISINAGE_S, ajouter

AUTRE_MAC = "02:a6:05:00:00:99"


@pytest.fixture
def autre_appareil():
    """Remplace l'Appareil d'une Caméra simulée (par numéro) par un autre, à la même IP."""
    yield lambda numero: deplacer_cameras_simulees({numero: IPS_SIMULEES[numero]}, {numero: AUTRE_MAC})
    remettre_cameras_simulees()


def attendre_camera(client: httpx.Client, id_camera: int, **attendus) -> dict:
    """Caméra dès que ses champs valent `attendus` ; la table de voisinage peut garder l'ancienne MAC un temps."""
    echeance = time.monotonic() + DELAI_VOISINAGE_S
    while True:
        camera = client.get(f"/api/cameras/{id_camera}").json()
        vus = {champ: camera[champ] for champ in attendus}
        if vus == attendus:
            return camera
        assert time.monotonic() < echeance, f"Caméra {vus}, attendu {attendus}"
        time.sleep(0.5)


def test_autre_appareil_offline_plus_relaye_puis_retabli_a_son_retour(connecte, essai, autre_appareil):
    camera = ajouter(essai, 1)
    attendre_camera(connecte, camera["id"], etat="online", raison_etat=None)
    attendre_lisible(camera["chemin_flux"], True)

    autre_appareil(1)

    remplacee = attendre_camera(connecte, camera["id"], etat="offline", raison_etat="autre_appareil")
    assert remplacee["mac"] == MACS_SIMULEES[1]
    attendre_lisible(camera["chemin_flux"], False)

    remettre_cameras_simulees()

    attendre_camera(connecte, camera["id"], etat="online", raison_etat=None)
    attendre_lisible(camera["chemin_flux"], True)


def test_camera_sans_mac_remplie_par_la_sonde(connecte, creer_camera):
    # Par son nom Compose : la sonde résout l'hôte de l'URL pour lire la MAC de son IP.
    camera = creer_camera(url_rtsp=url_camera_simulee(3, unique("sonde"))).json()
    assert camera["mac"] is None

    remplie = attendre_camera(connecte, camera["id"], mac=MACS_SIMULEES[3])

    assert remplie["etat"] == "online"
    assert remplie["raison_etat"] is None


def test_camera_injoignable_garde_sa_mac_inconnue(connecte, creer_camera):
    camera = creer_camera(url_rtsp=f"rtsp://{unique('hote')}.invalid/flux").json()

    hors_ligne = attendre_camera(connecte, camera["id"], etat="offline")

    assert hors_ligne["mac"] is None
    assert hors_ligne["raison_etat"] is None
