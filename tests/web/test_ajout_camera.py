"""Ajout d'une Caméra depuis un Candidat, de bout en bout dans Chromium : l'Aperçu arrive vraiment en WebRTC."""

import re

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from stack_compose import EXPIRATION_APERCU_S, adresses_ip, url_camera_simulee
from test_administration import administration, api, noms, unique  # noqa: F401 (fixtures)
from test_detection import DELAI_DETECTION_MS

# Essai, puis démarrage à la demande du relais de l'Aperçu, avec de la marge.
DELAI_APERCU_MS = 45_000

# media/simulated/README.md
MOT_DE_PASSE_SIMULEE_2 = "argos-simulee"
# Adresse privée du sous-réseau de simulation où aucun conteneur ne répond.
IP_SANS_CAMERA = "172.30.0.250"


@pytest.fixture
def sans_essai(api):
    yield
    api.delete("/api/essai")


def test_ajout_depuis_un_candidat_au_flux_ouvert(administration: Page, noms, sans_essai):
    (ip,) = adresses_ip("camera-simulee-1")
    nom = noms("Ajout")
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)

    candidats.get_by_role("row").filter(has_text=ip).get_by_role("button", name="Ajouter").click()

    panneau = section.get_by_role("form", name=f"Ajouter {ip}:554")
    apercu = panneau.locator("video")
    expect(apercu).to_be_visible(timeout=DELAI_APERCU_MS)
    administration.wait_for_function(
        "(video) => video.currentTime > 0", arg=apercu.element_handle(), timeout=DELAI_APERCU_MS
    )
    expect(panneau.get_by_text("que le navigateur ne sait pas lire")).to_have_count(0)

    panneau.get_by_label("Nom").fill(nom)
    panneau.get_by_label("Emplacement").fill("Portail")
    panneau.get_by_role("button", name="Ajouter la Caméra").click()

    expect(administration.get_by_role("row").filter(has_text=nom).first).to_contain_text("Portail")
    expect(panneau).to_have_count(0)
    expect(candidats.get_by_role("row").filter(has_text=ip)).to_have_count(0)
    deja = section.get_by_role("group").filter(has_text=re.compile(r"Déjà configurées \(\d+\)"))
    deja.get_by_text(re.compile(r"Déjà configurées \(\d+\)")).click()
    expect(deja.get_by_role("row").filter(has_text=nom)).to_contain_text(ip)


def test_annuler_ferme_le_panneau_sans_rien_creer(administration: Page, api, sans_essai):
    (ip,) = adresses_ip("camera-simulee-1")
    avant = len(api.get("/api/cameras").json())
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)
    candidats.get_by_role("row").filter(has_text=ip).get_by_role("button", name="Ajouter").click()
    panneau = section.get_by_role("form", name=f"Ajouter {ip}:554")
    expect(panneau.locator("video")).to_be_visible(timeout=DELAI_APERCU_MS)

    panneau.get_by_role("button", name="Annuler").click()

    expect(panneau).to_have_count(0)
    expect(candidats.get_by_role("row").filter(has_text=ip)).to_be_visible()
    assert len(api.get("/api/cameras").json()) == avant


def test_l_apercu_reste_tant_que_le_panneau_est_ouvert_et_annuler_le_retire(administration: Page, api, sans_essai):
    (ip,) = adresses_ip("camera-simulee-1")
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)
    candidats.get_by_role("row").filter(has_text=ip).get_by_role("button", name="Ajouter").click()
    panneau = section.get_by_role("form", name=f"Ajouter {ip}:554")
    apercu = panneau.locator("video")
    expect(apercu).to_be_visible(timeout=DELAI_APERCU_MS)
    administration.wait_for_function(
        "(video) => video.currentTime > 0", arg=apercu.element_handle(), timeout=DELAI_APERCU_MS
    )

    administration.wait_for_timeout((EXPIRATION_APERCU_S + 5) * 1000)

    lu = apercu.evaluate("(video) => video.currentTime")
    administration.wait_for_function(
        "([video, lu]) => video.currentTime > lu", arg=[apercu.element_handle(), lu], timeout=DELAI_APERCU_MS
    )
    expect(panneau.get_by_role("alert")).to_have_count(0)

    panneau.get_by_role("button", name="Annuler").click()

    expect(panneau).to_have_count(0)
    # Le retrait part en arrière-plan : il arrive vite, bien avant l'expiration.
    for _ in range(10):
        if api.post("/api/essai/renouveler").status_code == 404:
            break
        administration.wait_for_timeout(500)
    assert api.post("/api/essai/renouveler").status_code == 404


def test_ajout_d_une_camera_a_mot_de_passe_apres_un_mauvais(administration: Page, noms, sans_essai):
    (ip,) = adresses_ip("camera-simulee-2")
    nom = noms("Ajout")
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)
    candidats.get_by_role("row").filter(has_text=ip).get_by_role("button", name="Ajouter").click()
    panneau = section.get_by_role("form", name=f"Ajouter {ip}:554")

    expect(panneau.get_by_text("Cette caméra demande un mot de passe")).to_be_visible(timeout=DELAI_APERCU_MS)
    expect(panneau.get_by_label("Identifiant")).to_have_value("admin")
    panneau.get_by_label("Mot de passe").fill("mauvais")
    panneau.get_by_role("button", name="Valider").click()

    expect(panneau.get_by_text("Identifiant ou mot de passe refusé par la caméra")).to_be_visible(
        timeout=DELAI_APERCU_MS
    )
    panneau.get_by_label("Mot de passe").fill(MOT_DE_PASSE_SIMULEE_2)
    panneau.get_by_role("button", name="Valider").click()

    apercu = panneau.locator("video")
    expect(apercu).to_be_visible(timeout=DELAI_APERCU_MS)
    administration.wait_for_function(
        "(video) => video.currentTime > 0", arg=apercu.element_handle(), timeout=DELAI_APERCU_MS
    )
    expect(panneau.get_by_label("Mot de passe")).to_have_count(0)
    panneau.get_by_label("Nom").fill(nom)
    panneau.get_by_role("button", name="Ajouter la Caméra").click()

    ligne = administration.get_by_role("row").filter(has_text=nom).first
    expect(ligne).to_be_visible()
    expect(ligne).not_to_contain_text(MOT_DE_PASSE_SIMULEE_2)
    expect(panneau).to_have_count(0)


def test_ajout_d_une_camera_au_chemin_exotique(administration: Page, noms, sans_essai):
    (ip,) = adresses_ip("camera-simulee-3")
    nom = noms("Ajout")
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)
    candidats.get_by_role("row").filter(has_text=ip).get_by_role("button", name="Ajouter").click()
    panneau = section.get_by_role("form", name=f"Ajouter {ip}:554")

    expect(panneau.get_by_text("Flux introuvable")).to_be_visible(timeout=DELAI_APERCU_MS)
    panneau.get_by_label("Chemin RTSP").fill("/flux")
    panneau.get_by_role("button", name="Valider").click()

    apercu = panneau.locator("video")
    expect(apercu).to_be_visible(timeout=DELAI_APERCU_MS)
    administration.wait_for_function(
        "(video) => video.currentTime > 0", arg=apercu.element_handle(), timeout=DELAI_APERCU_MS
    )
    expect(panneau.get_by_label("Chemin RTSP")).to_have_count(0)
    panneau.get_by_label("Nom").fill(nom)
    panneau.get_by_role("button", name="Ajouter la Caméra").click()

    expect(administration.get_by_role("row").filter(has_text=nom).first).to_be_visible()
    expect(panneau).to_have_count(0)


def test_un_codec_non_lisible_est_nomme_et_l_ajout_reste_permis(administration: Page, noms, sans_essai):
    (ip,) = adresses_ip("camera-simulee-1")
    nom = noms("Ajout")

    def en_h265(route: Route):
        # Le vrai essai ouvre l'Aperçu ; seul le codec annoncé change, comme une caméra en H.265.
        reponse = route.fetch()
        route.fulfill(response=reponse, json={**reponse.json(), "codec": "H265"})

    administration.route("**/api/essai", lambda route: en_h265(route) if route.request.method == "POST" else route.continue_())
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)
    candidats.get_by_role("row").filter(has_text=ip).get_by_role("button", name="Ajouter").click()
    panneau = section.get_by_role("form", name=f"Ajouter {ip}:554")

    expect(
        panneau.get_by_text(
            "Cette caméra émet en H.265, que le navigateur ne sait pas lire. La Caméra peut être ajoutée ; "
            "la lecture viendra dans une version future."
        )
    ).to_be_visible(timeout=DELAI_APERCU_MS)
    panneau.get_by_label("Nom").fill(nom)
    panneau.get_by_role("button", name="Ajouter la Caméra").click()

    expect(administration.get_by_role("row").filter(has_text=nom).first).to_be_visible()
    expect(panneau).to_have_count(0)


def ajouter_par_ip(administration: Page, ip: str) -> Locator:
    """Saisit l'IP (port 554 par défaut) dans « Ajouter par adresse IP » et renvoie ce formulaire."""
    section = administration.get_by_role("region", name="Détecter des Caméras")
    formulaire = section.get_by_role("form", name="Ajouter par adresse IP")
    expect(formulaire.get_by_label("Port")).to_have_value("554")
    formulaire.get_by_label("Adresse IP").fill(ip)
    formulaire.get_by_role("button", name="Ajouter").click()
    return formulaire


def test_ajout_par_adresse_ip_sans_detection(administration: Page, noms, sans_essai):
    (ip,) = adresses_ip("camera-simulee-1")
    nom = noms("Ajout")

    ajouter_par_ip(administration, ip)

    panneau = administration.get_by_role("form", name=f"Ajouter {ip}:554")
    apercu = panneau.locator("video")
    expect(apercu).to_be_visible(timeout=DELAI_APERCU_MS)
    administration.wait_for_function(
        "(video) => video.currentTime > 0", arg=apercu.element_handle(), timeout=DELAI_APERCU_MS
    )
    panneau.get_by_label("Nom").fill(nom)
    panneau.get_by_role("button", name="Ajouter la Caméra").click()

    expect(administration.get_by_role("row").filter(has_text=nom).first).to_contain_text(ip)
    expect(panneau).to_have_count(0)


def test_ajout_par_adresse_ip_deja_configuree(administration: Page, api, noms, sans_essai):
    (ip,) = adresses_ip("camera-simulee-1")
    nom = noms()
    # Déclarée par son nom Compose : l'IP saisie est rapprochée de son IP résolue.
    assert api.post("/api/cameras", json={"nom": nom, "url_rtsp": url_camera_simulee(1, unique("ui"))}).status_code == 201

    formulaire = ajouter_par_ip(administration, ip)

    expect(formulaire.get_by_role("alert")).to_have_text(f"Déjà configurée : {nom}", timeout=DELAI_APERCU_MS)
    expect(administration.get_by_role("form", name=f"Ajouter {ip}:554")).to_have_count(0)


def test_ajout_par_adresse_ip_sans_camera(administration: Page, sans_essai):
    ajouter_par_ip(administration, IP_SANS_CAMERA)

    panneau = administration.get_by_role("form", name=f"Ajouter {IP_SANS_CAMERA}:554")
    expect(panneau.get_by_text("Aucune caméra ne répond à cette adresse")).to_be_visible(timeout=DELAI_APERCU_MS)
    expect(panneau.locator("video")).to_have_count(0)
