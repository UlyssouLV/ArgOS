"""ONVIF en clair, sur accord de l'Administrateur (docs/adr/0007-onvif-en-https-par-cle-memorisee.md).

La Caméra simulée 4 ne propose pas HTTPS : sans accord, seule la recherche du port (`GetSystemDateAndTime` sans
identifiants) lui parvient. La 2 propose HTTPS : l'accord ne la concerne jamais.
"""

from datetime import UTC, datetime, timedelta

import pytest

from stack_compose import client_du_site, remettre_onvif_en_usine, requetes_onvif_recues
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_reglages import camera_simulee, lire  # noqa: F401 (fixtures)
from test_reglages_https import (
    SIMULATEUR_2,
    camera_2_en_https,  # noqa: F401 (fixture)
    camera_lue,
    ip_api,  # noqa: F401 (fixture)
    journal_api,
    lignes_onvif,
    sans_https,  # noqa: F401 (fixture)
    sql,
)

SIMULATEUR_4 = "camera-simulee-4-onvif"
REFUS = {
    "code": "en_clair_non_accepte",
    "detail": "Cette caméra ne propose pas HTTPS : ONVIF en clair non accepté.",
}


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


def accorder(client, id_camera: int):
    return client.put(f"/api/cameras/{id_camera}/reglages/onvif-en-clair")


def retirer(client, id_camera: int):
    return client.delete(f"/api/cameras/{id_camera}/reglages/onvif-en-clair")


def recues_du_4(depuis: datetime, ip_api: str) -> list[str]:
    return requetes_onvif_recues(SIMULATEUR_4, depuis, ip_api, "http:80")


def test_simulee_4_refusee_sans_autre_requete_que_la_sonde(connecte, camera_simulee, ip_api):
    id_camera = camera_simulee(4, en_clair=False)
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    lecture = lire(connecte, id_camera)
    modification = connecte.patch(
        f"/api/cameras/{id_camera}/reglages", json={"incrustations": {"nom": {"texte": "Clair"}}}, timeout=30
    )
    mise_a_l_heure = connecte.post(f"/api/cameras/{id_camera}/reglages/mise-a-l-heure", timeout=30)

    for reponse in (lecture, modification, mise_a_l_heure):
        assert reponse.status_code == 502
        assert reponse.json() == REFUS
    # Une sonde par échange, rien d'autre.
    recues = recues_du_4(depuis, ip_api)
    assert len(recues) == 3
    assert all('"POST /onvif/device_service ' in ligne for ligne in recues)
    assert camera_lue(connecte, id_camera)["onvif_en_clair_accepte"] is False


def test_accord_puis_lecture_et_modification_puis_retrait(connecte, camera_simulee, ip_api):
    id_camera = camera_simulee(4, en_clair=False)
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    assert accorder(connecte, id_camera).status_code == 204

    assert camera_lue(connecte, id_camera)["onvif_en_clair_accepte"] is True
    lecture = lire(connecte, id_camera)
    assert lecture.status_code == 200
    assert lecture.json()["securite"] == {
        "chiffre": False,
        "empreinte": None,
        "empreinte_memorisee_le": None,
        "tls_ancien": False,
        "mot_de_passe_court": False,
    }
    modification = connecte.patch(
        f"/api/cameras/{id_camera}/reglages", json={"incrustations": {"nom": {"texte": "Clair"}}}, timeout=30
    )
    assert modification.status_code == 200
    assert modification.json()["champs"][0]["statut"] == "pris"
    remettre_onvif_en_usine()

    assert retirer(connecte, id_camera).status_code == 204

    assert camera_lue(connecte, id_camera)["onvif_en_clair_accepte"] is False
    assert lire(connecte, id_camera).json() == REFUS
    accord, retrait = lignes_onvif(journal_api(depuis), id_camera)
    assert "ONVIF en clair accepté" in accord
    assert "ONVIF en clair retiré" in retrait


def test_camera_reglee_en_http_avant_l_accord_le_demande(connecte, camera_simulee):
    id_camera = camera_simulee(4, en_clair=False)
    # Comme une Caméra réglée en 0.6.0 : HTTP sur 80, sans accord.
    sql(f"UPDATE cameras SET schema_onvif = 'http', port_onvif = 80 WHERE id = {id_camera}")

    assert lire(connecte, id_camera).json() == REFUS


def test_https_jamais_concerne_par_l_accord(connecte, camera_simulee, ip_api):
    id_camera = camera_simulee(2)
    assert accorder(connecte, id_camera).status_code == 204
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert reponse.json()["securite"]["chiffre"] is True
    assert reponse.json()["securite"]["mot_de_passe_court"] is False
    assert requetes_onvif_recues(SIMULATEUR_2, depuis, ip_api, "http:8899") == []


@pytest.mark.parametrize(
    ("mot_de_passe", "court"),
    [
        ("x", True),
        ("x" * 11, True),
        # 11 caractères une fois décodés, 66 dans l'URL.
        ("%C3%A9" * 11, True),
        ("x" * 12, False),
        ("", False),
    ],
)
def test_mot_de_passe_court_rappele_en_clair(connecte, camera_simulee, mot_de_passe, court):
    id_camera = camera_simulee(4, identifiants=f"admin:{mot_de_passe}")

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert reponse.json()["securite"]["mot_de_passe_court"] is court
    # Ni le mot de passe ni sa longueur : seulement « court » ou non.
    assert set(reponse.json()["securite"]) == {
        "chiffre",
        "empreinte",
        "empreinte_memorisee_le",
        "tls_ancien",
        "mot_de_passe_court",
    }
    if len(mot_de_passe) > 1:
        assert mot_de_passe not in reponse.text


def test_sans_identifiants_pas_de_mot_de_passe_court(connecte, camera_simulee):
    id_camera = camera_simulee(4, identifiants="")

    assert lire(connecte, id_camera).json()["securite"]["mot_de_passe_court"] is False


def test_https_disparu_refuse_meme_avec_l_accord(connecte, camera_2_en_https, sans_https, ip_api):
    id_camera, _ = camera_2_en_https
    assert accorder(connecte, id_camera).status_code == 204
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    reponse = lire(connecte, id_camera)

    assert reponse.json()["code"] == "https_indisponible"
    assert requetes_onvif_recues(SIMULATEUR_2, depuis, ip_api, "http:8899") == []


def test_accord_et_retrait_exigent_la_session(connecte, camera_simulee):
    id_camera = camera_simulee(4, en_clair=False)
    with client_du_site() as anonyme:
        assert accorder(anonyme, id_camera).status_code == 401
        assert retirer(anonyme, id_camera).status_code == 401
    assert camera_lue(connecte, id_camera)["onvif_en_clair_accepte"] is False


def test_accord_d_une_camera_inconnue_404(connecte):
    assert accorder(connecte, 999_999_999).status_code == 404
    assert retirer(connecte, 999_999_999).status_code == 404
