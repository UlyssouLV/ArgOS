"""Caméra muette après un changement d'Encodage (`ONVIF_SILENCE_APRES_ENCODAGE_S`) : le cas « sans réponse ».

Comme une vraie caméra qui relance son encodeur, elle accepte la modification puis ferme chaque connexion sans
répondre pendant le délai donné, sur tous ses services ; ensuite, elle répond de nouveau, modification retenue.
"""

import http.client
import time
import urllib.error

import pytest

from conftest import CHEMINS_RTSP_2, IDENTIFIANTS, Camera, _lancer
from test_https import Lancement, _port_libre
from test_media_2 import ENCODEUR_PRINCIPAL, encodeur, lire_encodeurs, regler_encodeur

SILENCE_S = 0.5


@pytest.fixture
def camera_muette_apres_encodage():
    yield from _lancer(
        IDENTIFIANTS,
        services=frozenset({"image", "media2"}),
        chemins_rtsp=CHEMINS_RTSP_2,
        silence_apres_encodage_s=SILENCE_S,
    )


def _muette(camera) -> bool:
    try:
        camera.appeler("<tds:GetSystemDateAndTime/>")
    except (urllib.error.URLError, http.client.RemoteDisconnected, ConnectionError):
        return True
    return False


def test_muette_apres_l_encodage_puis_repond_modification_retenue(camera_muette_apres_encodage):
    camera = camera_muette_apres_encodage
    # Adresse du média 2 lue avant : pendant le silence, GetServices non plus ne répond pas.
    services = camera.services()

    reponse = regler_encodeur(camera, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 2048))

    assert reponse.statut == 200 and reponse.faute is None
    assert _muette(camera)
    time.sleep(SILENCE_S + 0.2)
    assert not _muette(camera)
    assert camera.services() == services
    assert lire_encodeurs(camera)[ENCODEUR_PRINCIPAL]["resolution"] == ("1920", "1080")


def test_modification_refusee_ne_rend_pas_muette(camera_muette_apres_encodage):
    reponse = regler_encodeur(camera_muette_apres_encodage, encodeur(ENCODEUR_PRINCIPAL, 800, 448, 15, 2048))

    assert reponse.faute == "ter:ConfigModify"
    assert not _muette(camera_muette_apres_encodage)


def test_sans_la_variable_jamais_muette(camera_complete):
    regler_encodeur(camera_complete, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 2048))

    assert not _muette(camera_complete)


def test_silence_lu_au_lancement():
    port = _port_libre()
    with Lancement({"ONVIF_PORT": str(port), "ONVIF_SERVICES": "media2", "ONVIF_SILENCE_APRES_ENCODAGE_S": "30"}):
        camera = Camera(f"http://127.0.0.1:{port}", None)
        regler_encodeur(camera, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 2048))

        assert _muette(camera)
