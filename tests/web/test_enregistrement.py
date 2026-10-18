"""Interrupteur et indicateur d'enregistrement dans l'Administration."""

from playwright.sync_api import Page, Route, expect

from test_administration import administration, api, creer, ligne, noms, url_injoignable, url_simulee  # noqa: F401
from test_mac import cellule

DELAI_ONLINE_MS = 45_000


def test_interrupteur_et_indicateur_dans_la_liste(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())
    camera = ligne(administration, nom)
    tableau = administration.get_by_role("table").filter(has=administration.get_by_role("columnheader", name="Nom"))
    interrupteur = camera.get_by_role("switch", name="Enregistrement")
    identifiant = next(c["id"] for c in api.get("/api/cameras").json() if c["nom"] == nom)

    expect(administration.get_by_role("columnheader", name="Enregistrement")).to_be_visible()
    expect(interrupteur).to_be_visible()
    expect(interrupteur).not_to_be_checked()
    expect(cellule(tableau, camera, "Enregistrement")).to_contain_text("à l'arrêt")
    expect(cellule(tableau, camera, "Enregistrement")).to_contain_text("aucun segment")
    expect(cellule(tableau, camera, "Enregistrement")).to_contain_text(f"/enregistrements/camera-{identifiant}")


def test_interrupteur_allume_l_enregistrement_d_une_camera_en_ligne(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_simulee(1))
    camera = ligne(administration, nom)
    expect(camera).to_contain_text("online", timeout=DELAI_ONLINE_MS)

    camera.get_by_role("switch", name="Enregistrement").click()

    expect(camera.get_by_role("switch", name="Enregistrement")).to_be_checked()
    expect(camera.get_by_text("enregistre", exact=True)).to_be_visible()
    lue = next(c for c in api.get("/api/cameras").json() if c["nom"] == nom)
    assert lue["enregistrement"] is True
    assert lue["etat_enregistrement"] == "enregistre"


def test_indicateur_en_erreur_chemin_et_age_du_segment(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())
    camera = ligne(administration, nom)
    tableau = administration.get_by_role("table").filter(has=administration.get_by_role("columnheader", name="Nom"))

    def avec_indicateur(route: Route) -> None:
        reponse = route.fetch()
        cameras = [
            c
            | {
                "etat_enregistrement": "en_erreur",
                "dossier_enregistrement": "/enregistrements/camera-9",
                "age_dernier_segment_s": 75,
            }
            if c["nom"] == nom
            else c
            for c in reponse.json()
        ]
        route.fulfill(response=reponse, json=cameras)

    administration.route(
        "**/api/cameras",
        lambda route: avec_indicateur(route) if route.request.method == "GET" else route.continue_(),
    )
    administration.reload()

    indicateur = cellule(tableau, ligne(administration, nom), "Enregistrement")
    expect(indicateur).to_contain_text("en erreur")
    expect(indicateur).to_contain_text("/enregistrements/camera-9")
    expect(indicateur).to_contain_text("1 min")
    expect(indicateur).not_to_contain_text("aucun segment")


def test_interrupteur_desactive_sur_une_camera_desactivee(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())
    camera = ligne(administration, nom)
    camera.get_by_role("button", name="Désactiver").click()

    expect(camera.get_by_role("switch", name="Enregistrement")).to_be_disabled()
    expect(camera).to_contain_text("à l'arrêt")


def test_pas_de_lien_de_telechargement_ni_de_relecture_des_segments(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_injoignable())
    camera = ligne(administration, nom)

    expect(camera.get_by_role("link")).to_have_count(0)
    expect(administration.get_by_role("link", name="Télécharger")).to_have_count(0)
    expect(administration.get_by_text("relecture", exact=False)).to_have_count(0)
