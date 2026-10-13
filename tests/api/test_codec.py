"""Codec de chaque Caméra : relevé à l'ajout depuis l'essai, puis rafraîchi par la sonde, vu de l'extérieur de la stack.

Les Caméras simulées 1 (H.264) et 4 (H.265) servent le même chemin : la 4 rattachée à l'IP et à la MAC de la 1
est la même caméra reconfigurée en H.265. Chaque test remet les Caméras simulées à leur adresse d'origine.
"""

import time
from datetime import UTC, datetime

import httpx
import pytest

from stack_compose import (
    CHEMINS_SIMULES,
    IPS_SIMULEES,
    MACS_SIMULEES,
    compose,
    deplacer_cameras_simulees,
    remettre_cameras_simulees,
)
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_essai import essai  # noqa: F401 (fixture)
from test_etat_cameras import DELAI_ETAT_S, attendre_etat
from test_suivi_adresse import DELAI_VOISINAGE_S, ajouter

# Adresse libre du sous-réseau de simulation, hors de la plage dynamique (compose.simulation.yaml).
IP_LIBRE = "172.30.0.31"
AUTRE_MAC = "02:a6:05:00:00:98"


@pytest.fixture
def deplacer():
    yield deplacer_cameras_simulees
    remettre_cameras_simulees()


def url_a_l_ip(numero: int) -> str:
    """URL de la Caméra simulée par son IP, comme une caméra saisie à la main ; unique par sa requête."""
    return f"rtsp://{IPS_SIMULEES[numero]}/{CHEMINS_SIMULES[numero]}?test={unique('codec')}"


def attendre_codec(client: httpx.Client, id_camera: int, codec: str | None, delai: float = DELAI_ETAT_S) -> dict:
    echeance = time.monotonic() + delai
    while True:
        camera = client.get(f"/api/cameras/{id_camera}").json()
        if camera["codec"] == codec:
            return camera
        assert time.monotonic() < echeance, f"Codec {camera['codec']!r}, {codec!r} attendu"
        time.sleep(0.5)


def test_camera_simulee_4_ajoutee_depuis_l_essai_garde_h265(connecte, essai):
    assert essai(4)["codec"] == "H265"

    camera = ajouter(essai, 4)

    assert camera["codec"] == "H265"
    assert connecte.get(f"/api/cameras/{camera['id']}").json()["codec"] == "H265"


def test_camera_sans_codec_le_recoit_de_la_sonde(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_a_l_ip(1)).json()

    assert camera["codec"] is None
    assert attendre_codec(connecte, camera["id"], "H264")["etat"] == "online"


def test_codec_ni_cree_ni_modifie_par_l_administrateur(connecte, creer_camera):
    camera = creer_camera(codec="H265").json()

    modifiee = connecte.patch(f"/api/cameras/{camera['id']}", json={"codec": "H265"})

    assert camera["codec"] is None
    assert modifiee.status_code in (200, 422)
    assert connecte.get(f"/api/cameras/{camera['id']}").json()["codec"] is None


def test_codec_change_mis_a_jour_et_journalise(connecte, creer_camera, deplacer):
    camera = creer_camera(url_rtsp=url_a_l_ip(1)).json()
    attendre_codec(connecte, camera["id"], "H264")
    depuis = datetime.now(UTC).isoformat()

    # La caméra de l'IP 1, même Appareil (MAC), diffuse désormais en H.265.
    deplacer({1: IP_LIBRE, 4: IPS_SIMULEES[1]}, {1: AUTRE_MAC, 4: MACS_SIMULEES[1]})

    changee = attendre_codec(connecte, camera["id"], "H265", DELAI_VOISINAGE_S)
    assert changee["etat"] == "online"
    journaux = compose("logs", "--no-log-prefix", "--since", depuis, "api").stdout
    assert f"codec de la Caméra {camera['id']} : H264 → H265" in journaux


def test_sonde_sans_reponse_n_efface_pas_le_codec(connecte, creer_camera, deplacer):
    camera = creer_camera(url_rtsp=url_a_l_ip(1)).json()
    attendre_codec(connecte, camera["id"], "H264")

    deplacer({1: IP_LIBRE})

    hors_ligne = attendre_etat(connecte, camera["id"], "offline")
    assert hors_ligne["codec"] == "H264"
