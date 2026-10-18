"""Onglet Enregistrement : espace volume, Seuil de place disque et signal sous le seuil."""

import re

import pytest
from playwright.sync_api import Page, expect

from stack_compose import client_du_site
from test_connexion import se_connecter

SEUIL_DEFAUT = 1_073_741_824
SEUIL_MIN = 104_857_600
CONSERVATION_DEFAUT = 1
MO = 1_048_576


@pytest.fixture
def api(administrateur):
    with client_du_site() as client:
        assert client.post(
            "/api/session",
            json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
        ).status_code == 204
        yield client
        assert client.patch(
            "/api/reglages-site",
            json={"conservation_h": CONSERVATION_DEFAUT, "seuil_octets_libres": SEUIL_DEFAUT},
        ).status_code == 200


@pytest.fixture
def enregistrement(page: Page, administrateur) -> Page:
    page.goto("/enregistrement")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Enregistrement")).to_be_visible()
    return page


def test_page_affiche_total_libre_utilise(enregistrement: Page):
    expect(enregistrement.get_by_text("Total", exact=True)).to_be_visible(timeout=10_000)
    expect(enregistrement.get_by_text("Libre", exact=True)).to_be_visible()
    expect(enregistrement.get_by_text("Utilisé", exact=True)).to_be_visible()
    for libelle in ("Total", "Libre", "Utilisé"):
        expect(enregistrement.locator("dt", has_text=libelle).locator("xpath=../dd")).to_have_text(
            re.compile(r"[\d\s.,]+\s*(Mo|Go)")
        )


def test_regler_le_seuil_depuis_la_page(enregistrement: Page, api):
    champ = enregistrement.get_by_label("Seuil de place disque (Mo)")
    expect(champ).to_have_value(str(SEUIL_DEFAUT // MO), timeout=10_000)

    champ.fill("256")
    with enregistrement.expect_response(
        lambda r: r.url.endswith("/api/reglages-site") and r.request.method == "PATCH" and r.ok
    ):
        enregistrement.get_by_role("button", name="Enregistrer le seuil").click()

    expect(champ).to_have_value("256")
    assert api.get("/api/reglages-site").json()["seuil_octets_libres"] == 256 * MO


def test_signal_sous_le_seuil(enregistrement: Page, api):
    libre = api.get("/api/espace-enregistrements").json()["libre_o"]
    # Marge large : le libre du volume CI peut bouger de plusieurs Mo entre le PATCH et le reload.
    seuil = max(libre + SEUIL_DEFAUT, SEUIL_MIN)
    assert api.patch("/api/reglages-site", json={"seuil_octets_libres": seuil}).status_code == 200
    assert api.get("/api/espace-enregistrements").json()["sous_seuil"] is True

    enregistrement.reload()
    expect(enregistrement.get_by_role("heading", name="Enregistrement")).to_be_visible()
    expect(enregistrement.get_by_role("status")).to_contain_text("Place libre sous le seuil", timeout=10_000)
    expect(enregistrement.get_by_label("Place libre sous le seuil")).to_be_visible()


def test_pas_de_signal_quand_assez_de_place(enregistrement: Page, api):
    libre = api.get("/api/espace-enregistrements").json()["libre_o"]
    assert libre >= SEUIL_MIN, "prérequis : assez de place libre pour un seuil au plancher"
    assert api.patch("/api/reglages-site", json={"seuil_octets_libres": SEUIL_MIN}).status_code == 200
    enregistrement.reload()
    expect(enregistrement.get_by_role("heading", name="Enregistrement")).to_be_visible()
    expect(enregistrement.get_by_text("Total", exact=True)).to_be_visible(timeout=10_000)
    expect(enregistrement.get_by_role("status")).to_have_count(0)
