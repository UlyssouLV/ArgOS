"""Détection des Caméras dans l'Administration, de bout en bout dans Chromium."""

from playwright.sync_api import Page, expect

from stack_compose import adresses_ip
from test_administration import administration  # noqa: F401 (fixture)

# Un /24 sur deux ports tient en une dizaine de secondes : large marge.
DELAI_DETECTION_MS = 60_000


def test_detection_affiche_le_chargement_puis_les_candidats(administration: Page):
    cameras_simulees = sorted(ip for n in (1, 2, 3) for ip in adresses_ip(f"camera-simulee-{n}"))
    section = administration.get_by_role("region", name="Détecter des Caméras")
    expect(section).to_contain_text("172.30.0.0/24")

    section.get_by_role("button", name="Détecter des Caméras").click()

    expect(section.get_by_text("Détection en cours…")).to_be_visible()
    candidats = section.get_by_role("table", name="Candidats")
    expect(candidats).to_be_visible(timeout=DELAI_DETECTION_MS)
    for ip in cameras_simulees:
        expect(candidats.get_by_role("row").filter(has_text=ip)).to_contain_text("554")
    expect(section.get_by_text("Détection en cours…")).to_have_count(0)
