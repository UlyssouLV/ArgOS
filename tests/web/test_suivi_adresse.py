"""Suivi d'adresse d'un Appareil dans « Déjà configurées », de bout en bout dans Chromium.

`camera-simulee-3` est déplacée comme après un nouveau bail DHCP (stack_compose.deplacer_cameras_simulees),
puis remise à son adresse d'origine.
"""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import IPS_SIMULEES, deplacer_cameras_simulees, remettre_cameras_simulees
from test_administration import administration, api, noms  # noqa: F401 (fixtures)
from test_detection import DELAI_DETECTION_MS

# Adresse libre du sous-réseau de simulation, hors de la plage dynamique (compose.simulation.yaml).
NOUVELLE_IP = "172.30.0.33"
IP_SANS_APPAREIL = "172.30.0.99"


@pytest.fixture
def deplacer():
    yield deplacer_cameras_simulees
    remettre_cameras_simulees()


def ajouter_camera_simulee_3(api, nom: str) -> dict:
    """Depuis l'essai : URL à l'IP de camera-simulee-3, MAC lue."""
    essai = api.post("/api/essai", json={"ip": IPS_SIMULEES[3], "port": 554, "chemin": "flux"}, timeout=30)
    assert essai.json()["issue"] == "flux_trouve"
    reponse = api.post("/api/essai/camera", json={"nom": nom})
    api.delete("/api/essai")
    assert reponse.status_code == 201
    return reponse.json()


def deja_configurees(administration: Page) -> Locator:
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    resume = section.get_by_text(re.compile(r"Déjà configurées \(\d+\)"))
    expect(resume).to_be_visible(timeout=DELAI_DETECTION_MS)
    resume.click()
    return section.get_by_role("table", name="Déjà configurées")


def test_adresse_mise_a_jour_visible_apres_deplacement(administration: Page, api, noms, deplacer):
    nom = noms("Suivie")
    ajouter_camera_simulee_3(api, nom)
    deplacer({3: NOUVELLE_IP})

    ligne = deja_configurees(administration).get_by_role("row").filter(has_text=nom)

    expect(ligne).to_contain_text(NOUVELLE_IP)
    expect(ligne).to_contain_text(f"adresse mise à jour ({IPS_SIMULEES[3]} → {NOUVELLE_IP})")


def test_conflit_visible_sur_la_ligne_du_candidat(administration: Page, api, noms):
    nom, occupante = noms("Suivie"), noms("Occupante")
    camera = ajouter_camera_simulee_3(api, nom)
    ailleurs = camera["url_rtsp"].replace(IPS_SIMULEES[3], IP_SANS_APPAREIL)
    assert api.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": ailleurs}).status_code == 200
    assert api.post("/api/cameras", json={"nom": occupante, "url_rtsp": camera["url_rtsp"]}).status_code == 201

    ligne = deja_configurees(administration).get_by_role("row").filter(has_text=nom)

    expect(ligne).to_contain_text(IPS_SIMULEES[3])
    expect(ligne).to_contain_text(f"adresse non mise à jour : URL déjà prise par {occupante}")
