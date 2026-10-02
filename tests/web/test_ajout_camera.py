"""Ajout d'une Caméra depuis un Candidat, de bout en bout dans Chromium : l'Aperçu arrive vraiment en WebRTC."""

import re

import pytest
from playwright.sync_api import Page, expect

from stack_compose import adresses_ip
from test_administration import administration, api, noms  # noqa: F401 (fixtures)
from test_detection import DELAI_DETECTION_MS

# Essai, puis démarrage à la demande du relais de l'Aperçu, avec de la marge.
DELAI_APERCU_MS = 45_000


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
