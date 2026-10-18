"""Onglet Enregistrement : Conservation Site réglable (1–24 h)."""

import re

import pytest
from playwright.sync_api import Page, expect

from stack_compose import client_du_site
from test_connexion import se_connecter

CONSERVATION_DEFAUT = 1


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


def test_onglet_enregistrement_a_cote_d_administration_et_live(page: Page, administrateur):
    page.goto("/connexion")
    se_connecter(page, **administrateur)

    bandeau = page.get_by_role("banner")
    expect(bandeau.get_by_role("link", name="Administration")).to_be_visible()
    expect(bandeau.get_by_role("link", name="Enregistrement")).to_be_visible()
    expect(bandeau.get_by_role("link", name="Live")).to_be_visible()

    bandeau.get_by_role("link", name="Enregistrement").click()
    expect(page).to_have_url(re.compile(r"/enregistrement$"))
    expect(page.get_by_role("heading", name="Enregistrement")).to_be_visible()


def test_regler_la_conservation_depuis_la_page(enregistrement: Page, api):
    champ = enregistrement.get_by_label("Conservation (heures)")
    expect(champ).to_have_value(str(CONSERVATION_DEFAUT), timeout=10_000)

    champ.fill("4")
    with enregistrement.expect_response(
        lambda r: r.url.endswith("/api/reglages-site") and r.request.method == "PATCH" and r.ok
    ):
        enregistrement.get_by_role("button", name="Enregistrer la conservation").click()

    expect(champ).to_have_value("4")
    assert api.get("/api/reglages-site").json()["conservation_h"] == 4


def test_interrupteur_reste_dans_administration(enregistrement: Page):
    expect(enregistrement.get_by_role("switch", name="Enregistrement")).to_have_count(0)
    expect(enregistrement.get_by_text("reste dans Administration")).to_be_visible()
