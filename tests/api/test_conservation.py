"""Conservation Site : réglage 1–24 h, persistance et poussée `recordDeleteAfter` au pont."""

import json
import time

import pytest

from stack_compose import client_du_site, compose
from test_cameras import connecte, creer_camera  # noqa: F401

DELAI_PONT_S = 20
CONSERVATION_DEFAUT = 1


@pytest.fixture(autouse=True)
def conservation_remise_a_un(administrateur):
    """Le réglage est global au Site : chaque test repart de 1 h et y revient.

    Client dédié : ne pas réutiliser `client` / `connecte`, sinon les tests 401 voient une session.
    """

    def remettre() -> None:
        with client_du_site() as c:
            assert c.post(
                "/api/session",
                json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
            ).status_code == 204
            assert c.patch("/api/reglages-site", json={"conservation_h": CONSERVATION_DEFAUT}).status_code == 200

    remettre()
    yield
    remettre()


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


def _attendre_conservation(nom: str, heures: int) -> dict:
    attendu = f"{heures}h0m0s"
    config = None
    echeance = time.monotonic() + DELAI_PONT_S
    while time.monotonic() < echeance:
        try:
            config = _config_chemin(nom)
        except Exception:
            time.sleep(1)
            continue
        if config.get("recordDeleteAfter") == attendu:
            return config
        time.sleep(1)
    assert config is not None
    return config


def test_conservation_par_defaut_une_heure(connecte):
    reponse = connecte.get("/api/reglages-site")

    assert reponse.status_code == 200
    assert reponse.json()["conservation_h"] == CONSERVATION_DEFAUT


def test_conservation_sans_session_401(client):
    assert client.get("/api/reglages-site").status_code == 401
    assert client.patch("/api/reglages-site", json={"conservation_h": 2}).status_code == 401


def test_regler_la_conservation_la_persiste(connecte):
    reponse = connecte.patch("/api/reglages-site", json={"conservation_h": 6})

    assert reponse.status_code == 200
    assert reponse.json()["conservation_h"] == 6
    assert connecte.get("/api/reglages-site").json()["conservation_h"] == 6


def test_conservation_hors_bornes_refusee(connecte):
    avant = connecte.get("/api/reglages-site").json()["conservation_h"]
    for heures in (0, 25, -1):
        reponse = connecte.patch("/api/reglages-site", json={"conservation_h": heures})

        assert reponse.status_code == 422, heures
        assert connecte.get("/api/reglages-site").json()["conservation_h"] == avant


def test_changement_de_conservation_pousse_record_delete_after_au_pont(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch("/api/reglages-site", json={"conservation_h": 3}).status_code == 200

    config = _attendre_conservation(camera["chemin_flux"], 3)

    assert config["recordDeleteAfter"] == "3h0m0s"
