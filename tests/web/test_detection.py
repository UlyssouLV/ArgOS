"""Détection des Caméras dans une boîte de dialogue de la page Caméras, de bout en bout dans Chromium."""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import IPS_SIMULEES, adresses_ip
from test_administration import administration, api, noms, url_simulee  # noqa: F401 (fixtures)

# Un /24 sur deux ports tient en une dizaine de secondes : large marge.
DELAI_DETECTION_MS = 60_000


def ouvrir_detection(page: Page) -> Locator:
    """« Détecter des Caméras » en tête de page : la boîte de dialogue, qui lance la Détection."""
    page.get_by_role("button", name="Détecter des Caméras").first.click()
    boite = page.get_by_role("dialog", name="Détecter des Caméras")
    expect(boite).to_be_visible()
    return boite


def onglet(boite: Locator, nom: str) -> Locator:
    """Onglet « Candidats » ou « Déjà configurées », nommé avec son compteur : « Candidats (3) »."""
    return boite.get_by_role("tab", name=re.compile(rf"^{nom} \(\d+\)$"))


def tableau(boite: Locator, nom: str) -> Locator:
    """Tableau de l'onglet `nom`, une fois l'onglet choisi."""
    onglet(boite, nom).click()
    return boite.get_by_role("table", name=nom, exact=True)


def candidats(boite: Locator) -> Locator:
    """Tableau des Candidats, à la fin de la Détection."""
    tableau = boite.get_by_role("table", name="Candidats", exact=True)
    expect(tableau).to_be_visible(timeout=DELAI_DETECTION_MS)
    return tableau


def test_le_bouton_en_tete_ouvre_la_boite_et_lance_la_detection(administration: Page):
    cameras_simulees = sorted(ip for n in IPS_SIMULEES for ip in adresses_ip(f"camera-simulee-{n}"))

    boite = ouvrir_detection(administration)

    expect(boite).to_contain_text("172.30.0.0/24")
    expect(boite.get_by_text("Détection en cours…")).to_be_visible()
    tableau_candidats = candidats(boite)
    for ip in cameras_simulees:
        expect(tableau_candidats.get_by_role("row").filter(has_text=ip)).to_contain_text("554")
    expect(boite.get_by_text("Détection en cours…")).to_have_count(0)
    expect(onglet(boite, "Candidats")).to_have_attribute("aria-selected", "true")


@pytest.mark.parametrize("fermeture", ["Échap", "Fermer"])
def test_echap_ou_fermer_referme_la_boite(administration: Page, fermeture: str):
    boite = ouvrir_detection(administration)
    # La Détection va à son terme côté serveur : la suivante serait refusée tant qu'elle tourne.
    candidats(boite)

    if fermeture == "Échap":
        administration.keyboard.press("Escape")
    else:
        boite.get_by_role("button", name="Fermer").click()

    expect(boite).to_have_count(0)
    expect(administration.get_by_role("heading", name="Caméras", level=1)).to_be_visible()


def test_deja_configurees_dans_son_onglet_avec_le_nom(administration: Page, api, noms):
    nom = noms()
    assert api.post("/api/cameras", json={"nom": nom, "url_rtsp": url_simulee(1)}).status_code == 201
    (ip,) = adresses_ip("camera-simulee-1")
    boite = ouvrir_detection(administration)

    expect(candidats(boite).get_by_role("row").filter(has_text=ip)).to_have_count(0)
    expect(boite.get_by_text(nom)).to_have_count(0)

    deja = tableau(boite, "Déjà configurées")

    expect(onglet(boite, "Déjà configurées")).to_have_attribute("aria-selected", "true")
    expect(deja.get_by_role("row").filter(has_text=nom)).to_contain_text(ip)
    expect(boite.get_by_role("table", name="Candidats", exact=True)).to_have_count(0)


def test_compteurs_des_onglets(administration: Page, api, noms):
    (ip,) = adresses_ip("camera-simulee-1")
    assert api.post("/api/cameras", json={"nom": noms(), "url_rtsp": url_simulee(1)}).status_code == 201
    boite = ouvrir_detection(administration)
    lignes = candidats(boite).get_by_role("row")

    nouveaux = lignes.count() - 1  # la ligne d'en-tête
    expect(onglet(boite, "Candidats")).to_have_text(f"Candidats ({nouveaux})")
    deja = tableau(boite, "Déjà configurées").get_by_role("row")
    expect(onglet(boite, "Déjà configurées")).to_have_text(f"Déjà configurées ({deja.count() - 1})")
    expect(deja.filter(has_text=ip)).to_have_count(1)


def test_l_etat_vide_ouvre_la_boite(administration: Page):
    administration.route(
        "**/api/cameras",
        lambda route: route.fulfill(json=[]) if route.request.method == "GET" else route.continue_(),
    )
    administration.reload()

    administration.get_by_role("region", name="Aucune Caméra").get_by_role("button", name="Détecter des Caméras").click()

    expect(administration.get_by_role("dialog", name="Détecter des Caméras")).to_be_visible()


def test_une_detection_deja_en_cours_est_attendue(administration: Page):
    refus = {"restants": 2}

    def deja_en_cours(route):
        # Comme une Détection lancée d'un autre onglet : l'API refuse tant qu'elle tourne.
        if route.request.method == "POST" and refus["restants"]:
            refus["restants"] -= 1
            route.fulfill(status=409, json={"detail": "Une Détection est déjà en cours."})
        else:
            route.continue_()

    administration.route("**/api/detection", deja_en_cours)

    boite = ouvrir_detection(administration)

    expect(boite.get_by_text("Détection en cours…")).to_be_visible()
    candidats(boite)
    assert refus["restants"] == 0
    expect(boite.get_by_role("alert")).to_have_count(0)


def _arrets_tab(page: Page, boite: Locator, touche: str, nombre: int) -> list[str]:
    """Libellés des `nombre` arrêts suivants de `touche` (Tab, Shift+Tab) ; chacun doit tomber dans la boîte."""
    arrets = []
    for _ in range(nombre):
        page.keyboard.press(touche)
        assert boite.evaluate("b => b.contains(document.activeElement)"), f"focus sorti de la boîte après {arrets}"
        arrets.append(
            page.evaluate(
                "() => { const e = document.activeElement;"
                " return (e.labels?.[0]?.textContent ?? e.getAttribute('aria-label') ?? e.textContent).trim(); }"
            )
        )
    return arrets


def test_la_boite_se_parcourt_au_clavier(administration: Page):
    bouton = administration.get_by_role("button", name="Détecter des Caméras").first
    bouton.focus()
    administration.keyboard.press("Enter")
    boite = administration.get_by_role("dialog", name="Détecter des Caméras")
    candidats(boite)

    arrets = _arrets_tab(administration, boite, "Tab", 30)

    assert "Filtrer par MAC" in arrets
    assert any(re.fullmatch(r"Candidats \(\d+\)", a) for a in arrets)
    assert "Ajouter" in arrets
    assert "Relancer la Détection" in arrets
    assert "Adresse IP" in arrets

    # Relancer garde le focus dans la boîte, dans les deux sens.
    boite.get_by_role("button", name="Relancer la Détection").focus()
    administration.keyboard.press("Enter")
    expect(boite.get_by_text("Détection en cours…")).to_be_visible()
    assert boite.evaluate("b => b.contains(document.activeElement)")
    _arrets_tab(administration, boite, "Shift+Tab", 6)
    candidats(boite)
