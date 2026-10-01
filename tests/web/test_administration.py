"""Administration des Caméras dans l'UI, de bout en bout dans Chromium.

La base n'est jamais effacée : chaque test crée ses Caméras avec des noms et des URL uniques,
puis les désactive et les supprime par l'API.
"""

import re
import uuid

import httpx
import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import URL_API
from test_connexion import se_connecter

# Intervalle (10 s) + délai (5 s) de sonde, plus le rafraîchissement de la liste (10 s), avec de la marge.
DELAI_ONLINE_MS = 45_000


def unique(prefixe: str) -> str:
    return f"{prefixe}-{uuid.uuid4().hex[:12]}"


def url_simulee(chemin: str) -> str:
    """La requête rend l'URL unique (l'URL est unique parmi les Caméras) ; MediaMTX l'ignore."""
    return f"rtsp://mediamtx:8554/{chemin}?test={unique('ui')}"


def url_injoignable() -> str:
    return f"rtsp://{unique('hote')}.invalid/flux"


@pytest.fixture
def api(administrateur):
    with httpx.Client(base_url=URL_API, timeout=10) as client:
        assert client.post(
            "/api/session",
            json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
        ).status_code == 204
        yield client


@pytest.fixture
def noms(api):
    """Noms des Caméras du test : celles qui existent encore à la fin sont désactivées puis supprimées."""
    crees: list[str] = []

    def _nom(prefixe: str = "Caméra") -> str:
        crees.append(unique(prefixe))
        return crees[-1]

    yield _nom

    for camera in api.get("/api/cameras").json():
        if camera["nom"] in crees:
            assert api.patch(f"/api/cameras/{camera['id']}", json={"active": False}).status_code == 200
            assert api.delete(f"/api/cameras/{camera['id']}").status_code == 204


@pytest.fixture
def administration(page: Page, administrateur) -> Page:
    page.goto("/administration")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Administration")).to_be_visible()
    return page


def formulaire_creation(page: Page) -> Locator:
    return page.get_by_role("form", name="Nouvelle Caméra")


def creer(page: Page, nom: str, url: str, emplacement: str = "") -> None:
    formulaire = formulaire_creation(page)
    formulaire.get_by_label("Nom").fill(nom)
    formulaire.get_by_label("URL RTSP").fill(url)
    formulaire.get_by_label("Emplacement").fill(emplacement)
    formulaire.get_by_role("button", name="Créer").click()


def ligne(page: Page, nom: str) -> Locator:
    return page.get_by_role("row").filter(has_text=nom)


def test_camera_creee_apparait_puis_passe_online_sans_recharger(administration: Page, noms):
    nom = noms()

    creer(administration, nom, url_simulee("cam1"), "Portail")

    camera = ligne(administration, nom)
    expect(camera).to_contain_text("Portail")
    expect(camera).to_contain_text("mediamtx:8554")
    expect(camera).to_contain_text("active")
    expect(camera).to_contain_text("online", timeout=DELAI_ONLINE_MS)


def test_doublon_de_nom_affiche_le_409_dans_le_formulaire(administration: Page, noms, api):
    nom = noms()
    assert api.post("/api/cameras", json={"nom": nom, "url_rtsp": url_injoignable()}).status_code == 201

    creer(administration, nom, url_injoignable())

    expect(formulaire_creation(administration).get_by_role("alert")).to_contain_text(
        "Une Caméra porte déjà ce nom ou cette URL"
    )


def test_url_non_rtsp_affiche_un_message_dans_le_formulaire(administration: Page, noms):
    nom = noms()

    creer(administration, nom, "http://exemple.invalid/flux")

    expect(formulaire_creation(administration).get_by_role("alert")).to_contain_text("URL RTSP invalide")
    expect(ligne(administration, nom)).to_have_count(0)


def test_modifier_l_emplacement_conserve_le_mot_de_passe_rtsp(administration: Page, noms, api):
    nom = noms()
    url = f"rtsp://user:secret@{unique('hote')}.invalid/flux"
    creer(administration, nom, url, "Portail")
    expect(ligne(administration, nom)).to_contain_text("user:***@")

    ligne(administration, nom).get_by_role("button", name="Modifier").click()
    edition = administration.get_by_role("form", name=f"Modifier {nom}")
    expect(edition.get_by_label("URL RTSP")).to_have_value(re.compile(r"user:\*\*\*@"))
    edition.get_by_label("Emplacement").fill("Garage")
    edition.get_by_role("button", name="Enregistrer").click()

    expect(ligne(administration, nom)).to_contain_text("Garage")
    # L'URL stockée est toujours celle avec le vrai mot de passe : elle reste réservée.
    assert api.post("/api/cameras", json={"nom": noms(), "url_rtsp": url}).status_code == 409


def test_desactiver_puis_reactiver(administration: Page, noms):
    nom = noms()
    creer(administration, nom, url_injoignable())

    ligne(administration, nom).get_by_role("button", name="Désactiver").click()
    expect(ligne(administration, nom)).to_contain_text("désactivée")

    ligne(administration, nom).get_by_role("button", name="Réactiver").click()
    expect(ligne(administration, nom)).not_to_contain_text("désactivée")
    expect(ligne(administration, nom)).to_contain_text("active")


def test_supprimer_une_camera_desactivee_apres_confirmation(administration: Page, noms):
    nom = noms()
    creer(administration, nom, url_injoignable())
    camera = ligne(administration, nom)
    expect(camera.get_by_role("button", name="Désactiver")).to_be_visible()
    expect(camera.get_by_role("button", name="Supprimer")).to_have_count(0)

    camera.get_by_role("button", name="Désactiver").click()
    camera.get_by_role("button", name="Supprimer").click()
    expect(ligne(administration, nom)).to_have_count(1)  # rien n'est supprimé avant confirmation
    camera.get_by_role("button", name="Confirmer la suppression").click()

    expect(ligne(administration, nom)).to_have_count(0)
