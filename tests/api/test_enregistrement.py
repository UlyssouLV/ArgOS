"""Enregistrement par Caméra : champ API, règles, réconciliation du pont et purge du dossier."""

import json
import time

from stack_compose import compose
from test_cameras import connecte, creer_camera, sans_etat  # noqa: F401

DELAI_PONT_S = 20


def _ecrire_segment(id_camera: int) -> None:
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from pathlib import Path; "
        f"p = Path('/enregistrements/camera-{id_camera}'); p.mkdir(parents=True, exist_ok=True); "
        "(p / 'segment.mp4').write_text('x')",
    )


def _dossier_present(id_camera: int) -> bool:
    sortie = compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from pathlib import Path; "
        f"print(Path('/enregistrements/camera-{id_camera}').is_dir())",
    ).stdout.strip()
    return sortie == "True"


def _config_chemin(nom: str) -> dict:
    brut = compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "import urllib.request; "
        f"print(urllib.request.urlopen('http://mediamtx:9997/v3/config/paths/get/{nom}', timeout=5).read().decode())",
    ).stdout
    return json.loads(brut)


def _attendre_config(nom: str, record: bool, source_on_demand: bool) -> dict:
    config = None
    echeance = time.monotonic() + DELAI_PONT_S
    while time.monotonic() < echeance:
        try:
            config = _config_chemin(nom)
        except Exception:
            time.sleep(1)
            continue
        if config.get("record") is record and config.get("sourceOnDemand") is source_on_demand:
            return config
        time.sleep(1)
    assert config is not None
    return config


def test_enregistrement_off_a_l_ajout(creer_camera):
    assert creer_camera().json()["enregistrement"] is False


def test_patch_allume_et_eteint_l_enregistrement(connecte, creer_camera):
    camera = creer_camera().json()
    chemin = f"/api/cameras/{camera['id']}"

    allumee = connecte.patch(chemin, json={"enregistrement": True})
    eteinte = connecte.patch(chemin, json={"enregistrement": False})

    assert allumee.status_code == 200
    assert sans_etat(allumee.json()) == sans_etat(
        camera | {"enregistrement": True, "etat_enregistrement": "enregistre"}
    )
    assert eteinte.status_code == 200
    assert eteinte.json()["enregistrement"] is False
    assert eteinte.json()["etat_enregistrement"] == "a_l_arret"


def test_allumer_l_enregistrement_d_une_camera_desactivee_409(connecte, creer_camera):
    camera = creer_camera().json()
    chemin = f"/api/cameras/{camera['id']}"
    assert connecte.patch(chemin, json={"active": False}).status_code == 200

    reponse = connecte.patch(chemin, json={"enregistrement": True})

    assert reponse.status_code == 409
    assert connecte.get(chemin).json()["enregistrement"] is False


def test_desactiver_une_camera_coupe_l_enregistrement(connecte, creer_camera):
    camera = creer_camera().json()
    chemin = f"/api/cameras/{camera['id']}"
    assert connecte.patch(chemin, json={"enregistrement": True}).json()["enregistrement"] is True

    desactivee = connecte.patch(chemin, json={"active": False})

    assert desactivee.status_code == 200
    assert desactivee.json()["enregistrement"] is False
    assert desactivee.json()["active"] is False


def test_camera_active_enregistrement_on_le_pont_enregistre_sans_source_a_la_demande(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200

    config = _attendre_config(camera["chemin_flux"], record=True, source_on_demand=False)

    assert config["record"] is True
    assert config["sourceOnDemand"] is False


def test_camera_active_enregistrement_off_le_pont_reste_a_la_demande(connecte, creer_camera):
    camera = creer_camera().json()

    config = _attendre_config(camera["chemin_flux"], record=False, source_on_demand=True)

    assert config["record"] is False
    assert config["sourceOnDemand"] is True


def test_indicateur_a_l_arret_sans_segment_a_l_ajout(creer_camera):
    camera = creer_camera().json()

    assert camera["etat_enregistrement"] == "a_l_arret"
    assert camera["dossier_enregistrement"] == f"/enregistrements/camera-{camera['id']}"
    assert camera["age_dernier_segment_s"] is None


def test_indicateur_donne_l_age_du_dernier_segment_lu_sur_le_volume(connecte, creer_camera):
    camera = creer_camera().json()
    _ecrire_segment(camera["id"])

    lue = connecte.get(f"/api/cameras/{camera['id']}").json()

    assert lue["dossier_enregistrement"] == f"/enregistrements/camera-{camera['id']}"
    assert lue["age_dernier_segment_s"] is not None
    assert 0 <= lue["age_dernier_segment_s"] < 30
    assert lue["etat_enregistrement"] == "a_l_arret"


def test_indicateur_en_erreur_quand_l_enregistrement_est_allume_et_le_flux_mort(connecte, creer_camera):
    from test_etat_cameras import attendre_etat

    camera = creer_camera().json()
    attendre_etat(connecte, camera["id"], "offline")

    allumee = connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).json()

    assert allumee["enregistrement"] is True
    assert allumee["etat_enregistrement"] == "en_erreur"
    assert allumee["age_dernier_segment_s"] is None


def test_indicateur_en_erreur_si_le_dossier_n_est_pas_lisible(connecte, creer_camera):
    camera = creer_camera().json()
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from pathlib import Path; "
        f"Path('/enregistrements/camera-{camera['id']}').write_text('pas un dossier')",
    )

    lue = connecte.get(f"/api/cameras/{camera['id']}").json()

    assert lue["etat_enregistrement"] == "en_erreur"


def test_aucun_endpoint_de_telechargement_ni_de_lecture_des_segments(connecte, creer_camera):
    camera = creer_camera().json()
    identifiant = camera["id"]
    absents = (
        f"/api/cameras/{identifiant}/segments",
        f"/api/cameras/{identifiant}/enregistrements",
        f"/api/cameras/{identifiant}/enregistrement",
        "/api/enregistrements",
    )

    for chemin in absents:
        assert connecte.get(chemin).status_code == 404
    fichier = connecte.get(f"/enregistrements/camera-{identifiant}/segment.mp4")
    type_contenu = fichier.headers.get("content-type", "")
    assert "video" not in type_contenu
    assert "octet-stream" not in type_contenu
    chemins = connecte.get("/api/openapi.json").json()["paths"]
    assert not any("segment" in chemin for chemin in chemins)
    assert "/api/enregistrements" not in chemins


def test_suppression_d_une_camera_efface_son_dossier_d_enregistrement(connecte, creer_camera):
    camera = creer_camera().json()
    identifiant = camera["id"]
    chemin = f"/api/cameras/{identifiant}"
    _ecrire_segment(identifiant)
    assert _dossier_present(identifiant)
    assert connecte.patch(chemin, json={"active": False}).status_code == 200

    assert connecte.delete(chemin).status_code == 204

    assert not _dossier_present(identifiant)
