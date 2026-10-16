"""Image de l'Appareil dans les Réglages de la Caméra, lue et réglée par le service image ONVIF des Caméras simulées.

La 2 a le service image (WDR accepté sans être appliqué : le cas « pas pris »), la 4 n'en a pas. Ce que la caméra a
reçu se lit dans le journal de son simulateur, qui nomme l'opération SOAP de chaque requête.
"""

from datetime import UTC, datetime, timedelta

import pytest

from stack_compose import remettre_onvif_en_usine, requetes_onvif_recues
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_reglages import DELAI_LECTURE_S, USINE_INCRUSTATIONS, camera_simulee, champs, lire  # noqa: F401
from test_reglages_https import SIMULATEUR_2, ip_api  # noqa: F401 (fixture)

BORNES = {"min": 0, "max": 100}
USINE_IMAGE = {
    "reglable": True,
    "raison": None,
    "valeurs": {
        "infrarouge": "AUTO",
        "luminosite": 50,
        "contraste": 50,
        "saturation": 50,
        "nettete": 50,
        "contre_jour": "OFF",
        # La simulée 2 ne borne pas le niveau du contre-jour : ni lu, ni proposé.
        "contre_jour_niveau": None,
        "wdr": "OFF",
        "wdr_niveau": 50,
    },
    "options": {
        "infrarouge": ["ON", "OFF", "AUTO"],
        "luminosite": BORNES,
        "contraste": BORNES,
        "saturation": BORNES,
        "nettete": BORNES,
        "contre_jour": ["OFF", "ON"],
        "contre_jour_niveau": None,
        "wdr": ["OFF", "ON"],
        "wdr_niveau": BORNES,
    },
}
IMAGE_NON_REGLABLE = {"reglable": False, "raison": "non_reglable", "valeurs": None, "options": None}


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


@pytest.fixture
def remise_en_usine():
    yield
    remettre_onvif_en_usine()


def modifier(client, id_camera: int, reglages: dict):
    return client.patch(f"/api/cameras/{id_camera}/reglages", json=reglages, timeout=DELAI_LECTURE_S)


def operations_recues(depuis: datetime, ip_api: str) -> list[str]:
    """Opérations SOAP reçues par la simulée 2 depuis `depuis`, en HTTPS, venant de l'API."""
    return [ligne.rpartition(" ")[2] for ligne in requetes_onvif_recues(SIMULATEUR_2, depuis, ip_api, "https:443")]


def test_simulee_2_image_usine_et_options(connecte, camera_simulee):
    reponse = lire(connecte, camera_simulee(2))

    assert reponse.status_code == 200
    assert reponse.json()["image"] == USINE_IMAGE


def test_simulee_4_image_non_reglable_le_reste_lu_et_reglable(connecte, camera_simulee, remise_en_usine):
    id_camera = camera_simulee(4)

    reglages = lire(connecte, id_camera).json()

    assert reglages["image"] == IMAGE_NON_REGLABLE
    assert reglages["incrustations"] == USINE_INCRUSTATIONS
    assert reglages["horloge"]["fuseau_posix"] == "AWST-8"
    resultat = champs(modifier(connecte, id_camera, {"incrustations": {"nom": {"texte": "Portail"}}}))
    assert resultat["incrustations.nom.texte"]["statut"] == "pris"


def test_infrarouge_luminosite_et_contre_jour_pris_et_relus(connecte, camera_simulee, remise_en_usine):
    id_camera = camera_simulee(2)

    reponse = modifier(connecte, id_camera, {"image": {"infrarouge": "OFF", "luminosite": 70, "contre_jour": "ON"}})

    assert champs(reponse) == {
        "image.infrarouge": {"demande": "OFF", "relu": "OFF", "statut": "pris"},
        "image.luminosite": {"demande": 70, "relu": 70, "statut": "pris"},
        "image.contre_jour": {"demande": "ON", "relu": "ON", "statut": "pris"},
    }
    valeurs = lire(connecte, id_camera).json()["image"]["valeurs"]
    assert (valeurs["infrarouge"], valeurs["luminosite"], valeurs["contre_jour"]) == ("OFF", 70, "ON")
    assert valeurs["contraste"] == 50


def test_wdr_accepte_mais_pas_applique_pas_pris(connecte, camera_simulee, remise_en_usine):
    reponse = modifier(connecte, camera_simulee(2), {"image": {"wdr": "ON", "wdr_niveau": 80, "nettete": 30}})

    assert champs(reponse) == {
        "image.wdr": {"demande": "ON", "relu": "OFF", "statut": "pas_pris"},
        "image.wdr_niveau": {"demande": 80, "relu": 50, "statut": "pas_pris"},
        "image.nettete": {"demande": 30, "relu": 30, "statut": "pris"},
    }


@pytest.mark.parametrize(
    "image",
    [
        {"luminosite": 150},
        {"saturation": -1},
        {"wdr_niveau": 101},
        # Niveau non borné par la caméra : non proposé.
        {"contre_jour_niveau": 10},
        {"infrarouge": "NUIT"},
    ],
    ids=["luminosite", "saturation", "niveau_wdr", "niveau_contre_jour", "infrarouge"],
)
def test_hors_des_options_422_sans_rien_envoyer(connecte, camera_simulee, ip_api, image):
    id_camera = camera_simulee(2)
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    reponse = modifier(connecte, id_camera, {"image": image, "incrustations": {"nom": {"texte": "Portail"}}})

    assert reponse.status_code == 422
    recues = operations_recues(depuis, ip_api)
    # Les options ont été relues, mais rien n'a été envoyé.
    assert "GetOptions" in recues
    assert not {"SetImagingSettings", "SetOSD"} & set(recues), recues
    assert lire(connecte, id_camera).json()["incrustations"] == USINE_INCRUSTATIONS


def test_image_sur_une_camera_sans_service_image_422(connecte, camera_simulee):
    assert modifier(connecte, camera_simulee(4), {"image": {"luminosite": 60}}).status_code == 422


def test_champ_d_image_inconnu_422(connecte, camera_simulee):
    assert modifier(connecte, camera_simulee(4), {"image": {"exposition": 10}}).status_code == 422
