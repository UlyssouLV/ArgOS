"""Connexion de l'Administrateur dans l'UI, de bout en bout dans Chromium."""

import re

import pytest
from playwright.sync_api import Locator, Page, Request, expect

from conftest import redemarrer_api


def se_connecter(page: Page, identifiant: str, mot_de_passe: str) -> None:
    page.get_by_label("Identifiant").fill(identifiant)
    page.get_by_label("Mot de passe").fill(mot_de_passe)
    page.get_by_role("button", name="Se connecter").click()


def rail(page: Page) -> Locator:
    return page.get_by_role("navigation", name="Navigation")


def test_bons_identifiants_ouvrent_le_live(page: Page, administrateur):
    page.goto("/connexion")

    se_connecter(page, **administrateur)

    expect(page).to_have_url(re.compile(r"/live$"))
    expect(page.get_by_role("complementary")).to_contain_text(administrateur["identifiant"])
    for entree in ("Live", "Enregistrement", "Relecture", "Caméras", "Heure du Site"):
        expect(rail(page).get_by_role("link", name=entree)).to_be_visible()


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


def test_administration_sans_session_renvoie_a_la_connexion_puis_aux_cameras(page: Page, administrateur):
    page.goto("/administration")

    expect(page).to_have_url(re.compile(r"/connexion$"))
    se_connecter(page, **administrateur)

    expect(page).to_have_url(re.compile(r"/administration/cameras$"))
    expect(page.get_by_role("heading", name="Caméras", level=1)).to_be_visible()


def test_deconnexion_renvoie_a_la_connexion_et_ferme_la_session(page: Page, administrateur):
    page.goto("/connexion")
    se_connecter(page, **administrateur)
    expect(page).to_have_url(re.compile(r"/live$"))

    page.get_by_role("button", name="Déconnexion").click()

    expect(page).to_have_url(re.compile(r"/connexion$"))
    page.goto("/live")
    expect(page).to_have_url(re.compile(r"/connexion$"))


def test_connexion_montre_le_logo_la_carte_et_la_version(page: Page):
    page.goto("/connexion")

    expect(page.get_by_role("img", name="ArgOS")).to_be_visible()
    expect(page.get_by_role("heading", name="Connexion au Site")).to_be_visible()
    expect(page.get_by_role("contentinfo")).to_have_text(re.compile(r"^ArgOS \S+$"))
    expect(page).to_have_title("Connexion · ArgOS")


@pytest.fixture
def connecte(page: Page, administrateur) -> Page:
    page.goto("/connexion")
    se_connecter(page, **administrateur)
    expect(page).to_have_url(re.compile(r"/live$"))
    return page


@pytest.mark.parametrize(
    ("entree", "chemin", "titre"),
    [
        ("Live", "/live", "Live"),
        ("Enregistrement", "/enregistrement", "Enregistrement"),
        ("Relecture", r"/relecture(/\d+)?", "Relecture"),
        ("Caméras", "/administration/cameras", "Caméras"),
        ("Heure du Site", "/administration/heure-du-site", "Heure du Site"),
    ],
)
def test_le_rail_mene_a_chaque_page_et_marque_l_entree_courante(connecte: Page, entree, chemin, titre):
    rail(connecte).get_by_role("link", name=entree).click()

    expect(connecte).to_have_url(re.compile(chemin + "$"))
    expect(connecte.get_by_role("heading", name=titre, level=1)).to_be_visible()
    expect(rail(connecte).get_by_role("link", name=entree)).to_have_attribute("aria-current", "page")
    expect(rail(connecte).locator("[aria-current=page]")).to_have_count(1)
    expect(connecte).to_have_title(f"{titre} · ArgOS")


def test_version_en_bas_du_rail_identique_a_la_connexion(page: Page, administrateur):
    page.goto("/connexion")
    version = page.get_by_role("contentinfo").inner_text().removeprefix("ArgOS ")
    se_connecter(page, **administrateur)

    expect(page.get_by_role("complementary")).to_contain_text(version)


def test_adresse_inconnue_mene_au_live(connecte: Page):
    connecte.goto("/nulle-part")

    expect(connecte).to_have_url(re.compile(r"/live$"))


def test_favicon_est_la_tete_du_logo(page: Page):
    page.goto("/connexion")

    assert page.locator("link[rel=icon]").get_attribute("href") == "/favicon.png"
    reponse = page.request.get("/favicon.png")
    assert reponse.ok
    assert reponse.headers["content-type"] == "image/png"


def test_aucune_ressource_chargee_depuis_internet(page: Page, administrateur):
    externes: list[str] = []

    def noter(requete: Request) -> None:
        if not requete.url.startswith(("https://localhost", "data:", "blob:")):
            externes.append(requete.url)

    page.on("request", noter)

    page.goto("/connexion")
    expect(page.get_by_role("heading", name="Connexion au Site")).to_be_visible()
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Live", level=1)).to_be_visible()
    # Inter (texte) et JetBrains Mono (version du rail) viennent du build web.
    page.wait_for_function(
        """() => ['Inter', 'JetBrains Mono'].every((famille) => [...document.fonts].some(
            (police) => police.family.replaceAll('"', '') === famille && police.status === 'loaded'))"""
    )

    assert externes == []
