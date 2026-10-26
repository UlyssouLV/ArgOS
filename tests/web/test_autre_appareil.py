"""Raison « autre appareil à cette adresse » dans l'Administration, de bout en bout dans Chromium.

`camera-simulee-1` est rattachée à sa propre IP avec une autre MAC : un autre Appareil y sert le même Flux
(stack_compose.deplacer_cameras_simulees), puis elle retrouve sa MAC d'origine.
"""

import time

import pytest
from playwright.sync_api import Page, expect

from stack_compose import CHEMINS_SIMULES, IPS_SIMULEES, MACS_SIMULEES, deplacer_cameras_simulees, remettre_cameras_simulees
from test_administration import administration, api, creer, ligne, noms, unique  # noqa: F401 (fixtures)

AUTRE_MAC = "02:a6:05:00:00:99"
# La table de voisinage d'`api` peut garder l'ancienne MAC un temps, plus le rafraîchissement de la liste.
DELAI_AUTRE_APPAREIL_MS = 100_000
DELAI_MAC_S = 45


@pytest.fixture
def autre_appareil():
    yield lambda: deplacer_cameras_simulees({1: IPS_SIMULEES[1]}, {1: AUTRE_MAC})
    remettre_cameras_simulees()


def attendre_mac(api, nom: str) -> None:
    """La sonde a lu la MAC de camera-simulee-1 : son Appareil est connu."""
    echeance = time.monotonic() + DELAI_MAC_S
    while not any(c["nom"] == nom and c["mac"] == MACS_SIMULEES[1] for c in api.get("/api/cameras").json()):
        assert time.monotonic() < echeance, "MAC jamais lue par la sonde"
        time.sleep(1)


def test_raison_autre_appareil_a_cote_de_l_etat(administration: Page, api, noms, autre_appareil):
    nom = noms("Remplacée")
    url = f"rtsp://{IPS_SIMULEES[1]}/{CHEMINS_SIMULES[1]}?test={unique('ui')}"
    creer(administration, api, nom, url)
    attendre_mac(api, nom)

    autre_appareil()

    expect(ligne(administration, nom)).to_contain_text(
        "Hors ligne (autre appareil à cette adresse)", timeout=DELAI_AUTRE_APPAREIL_MS
    )
