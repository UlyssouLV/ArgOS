"""Administration des Caméras dans l'UI, de bout en bout dans Chromium.

La base n'est jamais effacée : chaque test crée ses Caméras avec des noms et des URL uniques,
puis les désactive et les supprime par l'API.
"""

import re
import uuid

import httpx
import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import client_du_site, url_camera_simulee
from test_connexion import se_connecter

# Intervalle (10 s) + délai (5 s) de sonde, plus le rafraîchissement de la liste (10 s), avec de la marge.
DELAI_ONLINE_MS = 45_000


def unique(prefixe: str) -> str:
    return f"{prefixe}-{uuid.uuid4().hex[:12]}"


def url_simulee(numero: int) -> str:
    return url_camera_simulee(numero, unique("ui"))


def url_injoignable() -> str:
    return f"rtsp://{unique('hote')}.invalid/flux"


@pytest.fixture
def api(administrateur):
    with client_du_site() as client:
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
    page.goto("/administration/cameras")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Caméras", level=1)).to_be_visible()
    return page


def creer(page: Page, api: httpx.Client, nom: str, url: str, emplacement: str | None = None) -> None:
    """Par l'API : l'Administration n'offre plus d'ajout par URL. La page relue montre la Caméra sans attendre."""
    assert api.post("/api/cameras", json={"nom": nom, "url_rtsp": url, "emplacement": emplacement}).status_code == 201
    page.reload()


def ligne(page: Page, nom: str) -> Locator:
    return page.get_by_role("table", name="Caméras", exact=True).get_by_role("row").filter(has_text=nom)


def ouvrir_panneau(page: Page, nom: str) -> Locator:
    """« Réglages » de la ligne : le panneau latéral « Réglages de <nom> »."""
    ligne(page, nom).get_by_role("button", name="Réglages").click()
    panneau = page.get_by_role("dialog", name=f"Réglages de {nom}")
    expect(panneau).to_be_visible()
    return panneau


def general(panneau: Locator) -> Locator:
    return panneau.get_by_role("region", name="Général", exact=True)


def appliquer(panneau: Locator) -> None:
    panneau.get_by_role("button", name="Appliquer").click()


def toast(page: Page, texte: str) -> Locator:
    """Toast qui contient `texte` : résultat d'une action, en bas à droite, rôle `status`, hors du panneau."""
    return page.get_by_role("region", name=re.compile("^Notifications")).get_by_role("status").filter(has_text=texte)


def test_pas_de_formulaire_d_ajout_par_url(administration: Page):
    expect(administration.get_by_role("heading", name="Caméras", level=1)).to_be_visible()

    expect(administration.get_by_role("form", name="Nouvelle Caméra")).to_have_count(0)
    expect(administration.get_by_label("URL RTSP")).to_have_count(0)
    expect(administration.get_by_role("button", name="Créer")).to_have_count(0)


def test_colonnes_du_tableau(administration: Page, api, noms):
    creer(administration, api, noms(), url_injoignable())

    tableau = administration.get_by_role("table", name="Caméras", exact=True)
    expect(tableau.get_by_role("columnheader")).to_have_text(
        ["Nom", "Adresse", "État", "Flux", "Enregistrement", "Réglages"]
    )


def test_camera_creee_apparait_puis_passe_en_ligne_sans_recharger(administration: Page, api, noms):
    nom = noms()

    creer(administration, api, nom, url_simulee(1), "Portail")

    camera = ligne(administration, nom)
    expect(camera).to_contain_text("Portail")
    expect(camera).to_contain_text("camera-simulee-1")
    expect(camera).to_contain_text("En ligne", timeout=DELAI_ONLINE_MS)


def test_squelettes_pendant_le_chargement(administration: Page):
    administration.route("**/api/cameras", lambda route: None)  # la liste ne répond jamais
    administration.reload()

    expect(administration.get_by_label("Chargement des Caméras")).to_be_visible()
    expect(administration.get_by_role("table", name="Caméras", exact=True)).to_have_count(0)


def test_aucune_camera_etat_vide_avec_la_detection(administration: Page):
    administration.route(
        "**/api/cameras",
        lambda route: route.fulfill(json=[]) if route.request.method == "GET" else route.continue_(),
    )
    administration.reload()

    vide = administration.get_by_role("region", name="Aucune Caméra")
    expect(vide).to_contain_text("Aucune Caméra")
    expect(vide.get_by_role("button", name="Détecter des Caméras")).to_be_visible()
    expect(administration.get_by_role("table", name="Caméras", exact=True)).to_have_count(0)


def test_reglages_ouvrent_le_panneau_general_puis_fermer(administration: Page, api, noms):
    nom = noms()
    url = url_injoignable()
    creer(administration, api, nom, url, "Portail")

    panneau = ouvrir_panneau(administration, nom)

    expect(general(panneau).get_by_label("Nom", exact=True)).to_have_value(nom)
    expect(general(panneau).get_by_label("URL RTSP")).to_have_value(url)
    expect(general(panneau).get_by_label("Emplacement")).to_have_value("Portail")
    expect(general(panneau).get_by_role("switch", name="Caméra active")).to_be_checked()
    expect(general(panneau).get_by_role("switch", name="Enregistrement")).not_to_be_checked()
    expect(panneau.get_by_role("button", name="Appliquer")).to_be_disabled()
    # La liste reste derrière le panneau.
    expect(ligne(administration, nom)).to_have_count(1)

    panneau.get_by_role("button", name="Fermer").click()
    expect(panneau).to_have_count(0)


def test_doublon_de_nom_affiche_le_409_sous_le_champ_et_un_toast(administration: Page, noms, api):
    pris = noms()
    nom = noms()
    assert api.post("/api/cameras", json={"nom": pris, "url_rtsp": url_injoignable()}).status_code == 201
    creer(administration, api, nom, url_injoignable())

    panneau = ouvrir_panneau(administration, nom)
    champ = general(panneau).get_by_label("Nom", exact=True)
    champ.fill(pris)
    appliquer(panneau)

    expect(champ).to_have_accessible_description(re.compile("^Une Caméra porte déjà ce nom ou cette URL"))
    expect(toast(administration, "Réglages non appliqués : Une Caméra porte déjà ce nom ou cette URL")).to_be_visible()


def test_nom_vide_refuse_sous_le_champ_sans_envoi(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())
    envois: list[str] = []
    administration.on("request", lambda r: envois.append(r.url) if r.method == "PATCH" else None)

    panneau = ouvrir_panneau(administration, nom)
    champ = general(panneau).get_by_label("Nom", exact=True)
    champ.fill("  ")
    appliquer(panneau)

    expect(champ).to_have_accessible_description("Le nom est obligatoire.")
    assert envois == []


def test_url_non_rtsp_affiche_un_message_sous_le_champ(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())

    panneau = ouvrir_panneau(administration, nom)
    champ = general(panneau).get_by_label("URL RTSP")
    champ.fill("http://exemple.invalid/flux")
    appliquer(panneau)

    expect(champ).to_have_accessible_description(re.compile("^URL RTSP invalide"))


def test_modifier_l_url_d_une_camera_toast_de_succes(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())
    nouvelle = url_injoignable()

    panneau = ouvrir_panneau(administration, nom)
    general(panneau).get_by_label("URL RTSP").fill(nouvelle)
    appliquer(panneau)

    expect(toast(administration, f"Réglages de {nom} appliqués.")).to_be_visible()
    expect(general(panneau).get_by_label("URL RTSP")).to_have_value(nouvelle)
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    assert camera["url_rtsp"] == nouvelle


def test_modifier_l_emplacement_conserve_le_mot_de_passe_rtsp(administration: Page, noms, api):
    nom = noms()
    url = f"rtsp://user:secret@{unique('hote')}.invalid/flux"
    creer(administration, api, nom, url, "Portail")

    panneau = ouvrir_panneau(administration, nom)
    expect(general(panneau).get_by_label("URL RTSP")).to_have_value(re.compile(r"user:\*\*\*@"))
    general(panneau).get_by_label("Emplacement").fill("Garage")
    appliquer(panneau)

    expect(ligne(administration, nom)).to_contain_text("Garage")
    # L'URL stockée est toujours celle avec le vrai mot de passe : elle reste réservée.
    assert api.post("/api/cameras", json={"nom": noms(), "url_rtsp": url}).status_code == 409


def test_annuler_revient_aux_valeurs_de_la_camera(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())

    panneau = ouvrir_panneau(administration, nom)
    general(panneau).get_by_label("Nom", exact=True).fill("Autre nom")
    general(panneau).get_by_role("switch", name="Caméra active").click()
    panneau.get_by_role("button", name="Annuler").click()

    expect(general(panneau).get_by_label("Nom", exact=True)).to_have_value(nom)
    expect(general(panneau).get_by_role("switch", name="Caméra active")).to_be_checked()
    expect(panneau.get_by_role("button", name="Appliquer")).to_be_disabled()


def test_desactiver_puis_reactiver(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())

    panneau = ouvrir_panneau(administration, nom)
    general(panneau).get_by_role("switch", name="Caméra active").click()
    appliquer(panneau)
    expect(ligne(administration, nom)).to_contain_text("Désactivée")
    expect(general(panneau).get_by_role("switch", name="Enregistrement")).to_be_disabled()

    general(panneau).get_by_role("switch", name="Caméra active").click()
    appliquer(panneau)
    expect(ligne(administration, nom)).not_to_contain_text("Désactivée")


def test_supprimer_une_camera_desactivee_apres_confirmation(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())

    panneau = ouvrir_panneau(administration, nom)
    expect(panneau.get_by_role("button", name="Supprimer la Caméra")).to_be_disabled()
    general(panneau).get_by_role("switch", name="Caméra active").click()
    appliquer(panneau)

    panneau.get_by_role("button", name="Supprimer la Caméra").click()
    confirmation = administration.get_by_role("alertdialog", name=f"Supprimer {nom} ?")
    confirmation.get_by_role("button", name="Annuler").click()
    expect(confirmation).to_have_count(0)
    expect(ligne(administration, nom)).to_have_count(1)  # rien n'est supprimé sans confirmation

    panneau.get_by_role("button", name="Supprimer la Caméra").click()
    confirmation.get_by_role("button", name="Supprimer", exact=True).click()

    expect(toast(administration, f"Caméra {nom} supprimée.")).to_be_visible()
    expect(panneau).to_have_count(0)
    expect(ligne(administration, nom)).to_have_count(0)
