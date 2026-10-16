"""Encodage du Flux dans les Réglages de la Caméra, lu et réglé par ONVIF sur les Caméras simulées (ADR 0008).

La 2 a le média 2 et deux profils (flux principal et secondaire) aux chemins de son URL RTSP ; lancée sans média 2,
son Flux H.264 se règle par le média 1. La 4 n'a que le média 1, et son Flux est en H.265 : non réglable.
Le profil réglé est celui dont l'URL de flux a le chemin et la requête de l'URL RTSP de la Caméra : ces Caméras
sont créées sur ce chemin exact, le port RTSP (`:554`, ignoré par la correspondance) les distinguant des autres.
Ce que la caméra a reçu se lit dans le journal de son simulateur.
"""

import time
from datetime import UTC, datetime, timedelta

import pytest

from stack_compose import (
    camera_simulee_2_muette_apres_encodage,
    camera_simulee_2_sans_media_2,
    remettre_onvif_en_usine,
)
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_codec import attendre_codec
from test_reglages import DELAI_LECTURE_S, USINE_INCRUSTATIONS, camera_simulee, champs, lire  # noqa: F401
from test_reglages_https import ip_api  # noqa: F401 (fixture)
from test_reglages_image import modifier, operations_recues

# Relecture après un envoi d'Encodage : jusqu'à 20 s, plus la lecture et l'envoi.
DELAI_ENCODAGE_S = 60
CHEMINS_DU_PROFIL = {
    (2, "principal"): "cam/realmonitor?channel=1&subtype=0",
    (2, "secondaire"): "cam/realmonitor?channel=1&subtype=1",
    (4, "principal"): "Streaming/Channels/101",
}

USINE_PRINCIPAL = {
    "reglable": True,
    "raison": None,
    "profil": "mainStream",
    "valeurs": {
        "resolution": "2304x1296",
        "images_par_seconde": 20,
        "debit_max": 4096,
        "codec": "H264",
        "qualite": 4,
        "intervalle_images_cles": 40,
    },
    "options": {
        "resolutions": ["2304x1296", "1920x1080", "1280x720"],
        "images_par_seconde": {"min": 1, "max": 22},
        "debit_max": {"min": 512, "max": 8192},
    },
}
PROFIL_INTROUVABLE = {"reglable": False, "raison": "profil_introuvable", "profil": None, "valeurs": None, "options": None}
MODIFICATION = {"resolution": "1920x1080", "images_par_seconde": 15, "debit_max": 2048}


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


@pytest.fixture
def remise_en_usine():
    yield
    remettre_onvif_en_usine()


@pytest.fixture
def camera_du_profil(connecte, creer_camera):
    """Crée une Caméra dont l'URL RTSP a le chemin et la requête d'un profil de la caméra (`principal`,
    `secondaire`) ; ONVIF en clair accepté pour la 4, qui ne propose pas HTTPS."""

    def _creer(numero: int, flux: str = "principal") -> int:
        identifiants = "admin:argos-simulee@" if numero == 2 else ""
        url = f"rtsp://{identifiants}camera-simulee-{numero}:554/{CHEMINS_DU_PROFIL[numero, flux]}"
        reponse = creer_camera(url_rtsp=url)
        assert reponse.status_code == 201, reponse.text
        id_camera = reponse.json()["id"]
        if numero == 4:
            assert connecte.put(f"/api/cameras/{id_camera}/reglages/onvif-en-clair").status_code == 204
        return id_camera

    return _creer


def modifier_encodage(client, id_camera: int, encodage: dict, **autres):
    return client.patch(
        f"/api/cameras/{id_camera}/reglages", json={"encodage": encodage, **autres}, timeout=DELAI_ENCODAGE_S
    )


def test_simulee_2_encodage_du_flux_principal_lu_par_le_media_2(connecte, camera_du_profil):
    reponse = lire(connecte, camera_du_profil(2))

    assert reponse.status_code == 200
    assert reponse.json()["encodage"] == USINE_PRINCIPAL


def test_camera_du_flux_secondaire_lit_le_flux_secondaire(connecte, camera_du_profil):
    encodage = lire(connecte, camera_du_profil(2, "secondaire")).json()["encodage"]

    assert encodage["profil"] == "subStream"
    assert encodage["valeurs"]["resolution"] == "800x448"
    assert encodage["options"]["resolutions"] == ["800x448", "640x360", "352x288"]
    assert encodage["options"]["debit_max"] == {"min": 64, "max": 2048}


def test_url_rtsp_sans_profil_correspondant_profil_introuvable(connecte, camera_simulee):
    # Requête `test=…` en plus : ni le chemin ni la requête d'aucun profil.
    reglages = lire(connecte, camera_simulee(2)).json()

    assert reglages["encodage"] == PROFIL_INTROUVABLE
    assert reglages["incrustations"] == USINE_INCRUSTATIONS


def test_profil_introuvable_rien_a_regler_422(connecte, camera_simulee):
    assert modifier_encodage(connecte, camera_simulee(2), {"debit_max": 2048}).status_code == 422


def test_resolution_images_et_debit_pris_et_relus_le_reste_inchange(connecte, camera_du_profil, remise_en_usine):
    id_camera = camera_du_profil(2)

    reponse = modifier_encodage(connecte, id_camera, MODIFICATION)

    assert champs(reponse) == {
        "encodage.resolution": {"demande": "1920x1080", "relu": "1920x1080", "statut": "pris"},
        "encodage.images_par_seconde": {"demande": 15, "relu": 15, "statut": "pris"},
        "encodage.debit_max": {"demande": 2048, "relu": 2048, "statut": "pris"},
    }
    valeurs = lire(connecte, id_camera).json()["encodage"]["valeurs"]
    assert valeurs == {
        "resolution": "1920x1080",
        "images_par_seconde": 15,
        "debit_max": 2048,
        "codec": "H264",
        "qualite": 4,
        "intervalle_images_cles": 40,
    }


def test_flux_secondaire_regle_le_flux_principal_inchange(connecte, camera_du_profil, remise_en_usine):
    secondaire = camera_du_profil(2, "secondaire")

    resultat = champs(modifier_encodage(connecte, secondaire, {"resolution": "640x360"}))

    assert resultat["encodage.resolution"]["statut"] == "pris"
    principal = camera_du_profil(2)
    assert lire(connecte, principal).json()["encodage"]["valeurs"]["resolution"] == "2304x1296"


@pytest.mark.parametrize(
    "encodage",
    [
        {"resolution": "800x448"},
        {"resolution": "1920×1080"},
        {"images_par_seconde": 25},
        {"images_par_seconde": 0},
        {"debit_max": 9000},
        {"debit_max": 100},
    ],
    ids=["resolution_non_proposee", "resolution_illisible", "images_trop", "images_zero", "debit_trop", "debit_peu"],
)
def test_hors_des_options_422_sans_rien_envoyer(connecte, camera_du_profil, ip_api, encodage):
    id_camera = camera_du_profil(2)
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    reponse = modifier_encodage(connecte, id_camera, encodage, incrustations={"nom": {"texte": "Portail"}})

    assert reponse.status_code == 422
    recues = operations_recues(depuis, ip_api)
    assert "GetVideoEncoderConfigurationOptions" in recues
    assert not {"SetVideoEncoderConfiguration", "SetOSD"} & set(recues), recues
    assert lire(connecte, id_camera).json()["incrustations"] == USINE_INCRUSTATIONS


def test_champ_d_encodage_inconnu_422(connecte, camera_du_profil):
    assert modifier_encodage(connecte, camera_du_profil(2), {"codec": "H265"}).status_code == 422


def test_simulee_4_h265_sans_media_2_non_reglable_valeurs_en_lecture_seule(connecte, camera_du_profil):
    id_camera = camera_du_profil(4)
    attendre_codec(connecte, id_camera, "H265")

    reglages = lire(connecte, id_camera).json()

    encodage = reglages["encodage"]
    assert (encodage["reglable"], encodage["raison"], encodage["profil"]) == (False, "non_reglable", "mainStream")
    # Le codec est celui du Flux : le média 1 de la caméra le décrit en H.264.
    assert encodage["valeurs"]["codec"] == "H265"
    assert encodage["valeurs"]["resolution"] == "2304x1296"
    assert reglages["incrustations"] == USINE_INCRUSTATIONS
    assert modifier_encodage(connecte, id_camera, {"debit_max": 2048}).status_code == 422


@pytest.fixture
def simulee_2_sans_media_2():
    camera_simulee_2_sans_media_2()
    yield
    remettre_onvif_en_usine()


def test_repli_media_1_sur_un_flux_h264_regle_et_pris(connecte, camera_du_profil, simulee_2_sans_media_2):
    id_camera = camera_du_profil(2)
    attendre_codec(connecte, id_camera, "H264")

    encodage = lire(connecte, id_camera).json()["encodage"]
    assert encodage == USINE_PRINCIPAL
    resultat = champs(modifier_encodage(connecte, id_camera, MODIFICATION))

    assert {champ: r["statut"] for champ, r in resultat.items()} == {
        "encodage.resolution": "pris",
        "encodage.images_par_seconde": "pris",
        "encodage.debit_max": "pris",
    }
    valeurs = lire(connecte, id_camera).json()["encodage"]["valeurs"]
    assert (valeurs["codec"], valeurs["qualite"], valeurs["intervalle_images_cles"]) == ("H264", 4, 40)


def test_camera_relancee_quelques_secondes_relue_puis_pris(connecte, camera_du_profil, remise_en_usine):
    camera_simulee_2_muette_apres_encodage(5)
    id_camera = camera_du_profil(2)

    resultat = champs(modifier_encodage(connecte, id_camera, {"debit_max": 2048}))

    assert resultat["encodage.debit_max"] == {"demande": 2048, "relu": 2048, "statut": "pris"}


def test_camera_qui_ne_repond_plus_pas_pris_sans_reponse(connecte, camera_du_profil, remise_en_usine):
    camera_simulee_2_muette_apres_encodage(120)
    id_camera = camera_du_profil(2)
    debut = time.monotonic()

    reponse = modifier_encodage(connecte, id_camera, {"resolution": "1920x1080", "debit_max": 2048})

    assert reponse.status_code == 200, reponse.text
    assert time.monotonic() - debut >= 20
    resultat = {c["champ"]: c for c in reponse.json()["champs"]}
    for champ in ("encodage.resolution", "encodage.debit_max"):
        assert (resultat[champ]["statut"], resultat[champ]["raison"]) == ("pas_pris", "sans_reponse")
    # Réglages d'avant l'envoi : la caméra n'a pas été relue.
    assert reponse.json()["reglages"]["encodage"]["valeurs"]["resolution"] == "2304x1296"
