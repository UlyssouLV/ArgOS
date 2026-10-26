"""Page Enregistrement : Conservation Site réglable en jours + heures, de 1 h à 30 jours (ADR 0017)."""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import client_du_site
from test_administration import toast
from test_connexion import se_connecter

CONSERVATION_DEFAUT = 1
ERREUR_BORNES = "La Conservation va de 1 h à 30 jours."


@pytest.fixture
def api(administrateur):
    with client_du_site() as client:
        assert client.post(
            "/api/session",
            json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
        ).status_code == 204
        yield client
        assert client.patch("/api/reglages-site", json={"conservation_h": CONSERVATION_DEFAUT}).status_code == 200


@pytest.fixture
def enregistrement(page: Page, administrateur) -> Page:
    page.goto("/enregistrement")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Enregistrement")).to_be_visible()
    return page


def _regler(page: Page, jours: str, heures: str) -> None:
    conservation = page.get_by_role("group", name="Conservation")
    conservation.get_by_label("Jours").fill(jours)
    conservation.get_by_label("Heures").fill(heures)


def _carte_conservation(page: Page) -> Locator:
    return page.get_by_role("region", name="Conservation", exact=True)


def _enregistrer(page: Page) -> None:
    with page.expect_response(
        lambda r: r.url.endswith("/api/reglages-site") and r.request.method == "PATCH" and r.ok
    ):
        page.get_by_role("button", name="Enregistrer").click()


def test_entree_enregistrement_du_rail_a_cote_de_live_et_des_cameras(page: Page, administrateur):
    page.goto("/connexion")
    se_connecter(page, **administrateur)

    rail = page.get_by_role("navigation", name="Navigation")
    expect(rail.get_by_role("link", name="Live")).to_be_visible()
    expect(rail.get_by_role("link", name="Enregistrement")).to_be_visible()
    expect(rail.get_by_role("link", name="Caméras")).to_be_visible()

    rail.get_by_role("link", name="Enregistrement").click()
    expect(page).to_have_url(re.compile(r"/enregistrement$"))
    expect(page.get_by_role("heading", name="Enregistrement")).to_be_visible()


def test_conservation_lue_en_jours_et_heures(enregistrement: Page):
    conservation = enregistrement.get_by_role("group", name="Conservation")
    expect(conservation.get_by_label("Jours")).to_have_value("0", timeout=10_000)
    expect(conservation.get_by_label("Heures")).to_have_value(str(CONSERVATION_DEFAUT))
    expect(_carte_conservation(enregistrement).get_by_text(f"{CONSERVATION_DEFAUT} h", exact=True)).to_be_visible()


def test_sept_jours_enregistres_en_heures_et_affiches_en_jours(enregistrement: Page, api):
    expect(enregistrement.get_by_role("group", name="Conservation").get_by_label("Jours")).to_be_enabled(
        timeout=10_000
    )
    _regler(enregistrement, "7", "0")
    _enregistrer(enregistrement)

    assert api.get("/api/reglages-site").json()["conservation_h"] == 168
    expect(toast(enregistrement, "Réglages d’enregistrement enregistrés.")).to_be_visible()
    expect(_carte_conservation(enregistrement).get_by_text("7 j", exact=True)).to_be_visible()


def test_jours_et_heures_ensemble(enregistrement: Page, api):
    expect(enregistrement.get_by_role("group", name="Conservation").get_by_label("Jours")).to_be_enabled(
        timeout=10_000
    )
    _regler(enregistrement, "2", "6")
    _enregistrer(enregistrement)

    assert api.get("/api/reglages-site").json()["conservation_h"] == 54
    expect(_carte_conservation(enregistrement).get_by_text("2 j 6 h", exact=True)).to_be_visible()


def test_trente_jours_acceptes(enregistrement: Page, api):
    expect(enregistrement.get_by_role("group", name="Conservation").get_by_label("Jours")).to_be_enabled(
        timeout=10_000
    )
    _regler(enregistrement, "30", "0")
    _enregistrer(enregistrement)

    assert api.get("/api/reglages-site").json()["conservation_h"] == 720


@pytest.mark.parametrize(("jours", "heures"), [("30", "1"), ("0", "0")])
def test_conservation_hors_bornes_refusee_sous_le_champ(enregistrement: Page, api, jours, heures):
    conservation = enregistrement.get_by_role("group", name="Conservation")
    expect(conservation.get_by_label("Jours")).to_be_enabled(timeout=10_000)
    patchs: list[str] = []
    enregistrement.on("request", lambda r: patchs.append(r.url) if r.method == "PATCH" else None)

    _regler(enregistrement, jours, heures)
    enregistrement.get_by_role("button", name="Enregistrer").click()

    expect(conservation.get_by_label("Jours")).to_have_accessible_description(ERREUR_BORNES)
    expect(conservation.get_by_label("Heures")).to_have_attribute("aria-invalid", "true")
    assert patchs == []
    assert api.get("/api/reglages-site").json()["conservation_h"] == CONSERVATION_DEFAUT


def test_interrupteur_reste_dans_administration(enregistrement: Page):
    expect(enregistrement.get_by_role("switch", name="Enregistrement")).to_have_count(0)
    expect(enregistrement.get_by_text("reste dans Administration")).to_be_visible()
