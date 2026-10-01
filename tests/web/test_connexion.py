"""Connexion de l'Administrateur dans l'UI, de bout en bout dans Chromium."""

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import redemarrer_api


def se_connecter(page: Page, identifiant: str, mot_de_passe: str) -> None:
    page.get_by_label("Identifiant").fill(identifiant)
    page.get_by_label("Mot de passe").fill(mot_de_passe)
    page.get_by_role("button", name="Se connecter").click()


def test_bons_identifiants_ouvrent_la_zone_connectee(page: Page, administrateur):
    page.goto("/connexion")

    se_connecter(page, **administrateur)

    expect(page).to_have_url(re.compile(r"/administration$"))
    expect(page.get_by_role("banner")).to_contain_text(administrateur["identifiant"])
    expect(page.get_by_role("link", name="Administration")).to_be_visible()
    expect(page.get_by_role("link", name="Live")).to_be_visible()


@pytest.fixture
def compteur_remis_a_zero():
    # L'échec compte dans le frein à la force brute (en mémoire de l'API) : on le remet à zéro
    # pour ne pas approcher du 429 au fil des lancements.
    yield
    redemarrer_api()


def test_mauvais_mot_de_passe_affiche_une_erreur_et_reste_sur_la_connexion(
    page: Page, administrateur, compteur_remis_a_zero
):
    page.goto("/connexion")

    se_connecter(page, administrateur["identifiant"], administrateur["mot_de_passe"] + "x")

    expect(page.get_by_role("alert")).to_have_text("Identifiant ou mot de passe incorrect.")
    expect(page).to_have_url(re.compile(r"/connexion$"))


def test_page_connectee_sans_session_renvoie_a_la_connexion_puis_y_revient(page: Page, administrateur):
    page.goto("/live")

    expect(page).to_have_url(re.compile(r"/connexion$"))
    se_connecter(page, **administrateur)

    expect(page).to_have_url(re.compile(r"/live$"))
    expect(page.get_by_role("heading", name="Live")).to_be_visible()


def test_administration_sans_session_renvoie_a_la_connexion_puis_y_revient(page: Page, administrateur):
    page.goto("/administration")

    expect(page).to_have_url(re.compile(r"/connexion$"))
    se_connecter(page, **administrateur)

    expect(page).to_have_url(re.compile(r"/administration$"))


def test_deconnexion_renvoie_a_la_connexion_et_ferme_la_session(page: Page, administrateur):
    page.goto("/connexion")
    se_connecter(page, **administrateur)
    expect(page).to_have_url(re.compile(r"/administration$"))

    page.get_by_role("button", name="Déconnexion").click()

    expect(page).to_have_url(re.compile(r"/connexion$"))
    page.goto("/administration")
    expect(page).to_have_url(re.compile(r"/connexion$"))
