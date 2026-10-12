"""Filtre par MAC des Candidats, tapée telle qu'écrite sur l'étiquette, de bout en bout dans Chromium.

`camera-simulee-1` est configurée (« Déjà configurées »), `-2` est un nouveau Candidat, `-3` perd sa MAC
comme derrière un routeur (test_mac.sans_mac).
"""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import MACS_SIMULEES
from test_administration import administration, api, noms  # noqa: F401 (fixtures)
from test_detection import DELAI_DETECTION_MS
from test_mac import ip_de, sans_mac


@pytest.fixture
def section(administration: Page, api, noms) -> Locator:
    assert api.post("/api/essai", json={"ip": ip_de(1), "port": 554}, timeout=30).json()["issue"] == "flux_trouve"
    assert api.post("/api/essai/camera", json={"nom": noms()}).status_code == 201
    sans_mac(administration, "/api/detection", ip_de(3))
    section = administration.get_by_role("region", name="Détecter des Caméras")
    section.get_by_role("button", name="Détecter des Caméras").click()
    expect(section.get_by_role("table", name="Candidats")).to_be_visible(timeout=DELAI_DETECTION_MS)
    section.get_by_text(re.compile(r"Déjà configurées \(\d+\)")).click()
    return section


def visibles(section: Locator, tableau: str) -> Locator:
    return section.get_by_role("table", name=tableau, exact=True).get_by_role("row")


def filtrer(section: Locator, saisie: str) -> None:
    section.get_by_role("textbox", name="Filtrer par MAC").fill(saisie)


def attendre_seulement(section: Locator, tableau: str, numero: int) -> None:
    rangees = visibles(section, tableau)
    expect(rangees.filter(has_text=ip_de(numero))).to_have_count(1)
    for autre in {1, 2, 3} - {numero}:
        expect(rangees.filter(has_text=ip_de(autre))).to_have_count(0)


@pytest.mark.parametrize(
    "saisie",
    [MACS_SIMULEES[2], MACS_SIMULEES[2].upper().replace(":", "-"), "02a6.0500.0002", " 02A605000002 "],
)
def test_filtre_par_mac_complete_dans_plusieurs_formats(section: Locator, saisie: str):
    filtrer(section, saisie)

    attendre_seulement(section, "Candidats", 2)
    expect(section.get_by_role("table", name="Déjà configurées")).to_have_count(0)


@pytest.mark.parametrize("saisie", ["00:01", "0-01", "0001"])
def test_filtre_par_mac_partielle_dans_deja_configurees(section: Locator, saisie: str):
    filtrer(section, saisie)

    attendre_seulement(section, "Déjà configurées", 1)
    expect(section.get_by_role("table", name="Candidats")).to_have_count(0)


def test_candidat_sans_mac_masque_des_qu_un_filtre_est_saisi(section: Locator):
    filtrer(section, "02:A6")

    expect(visibles(section, "Candidats").filter(has_text=ip_de(2))).to_have_count(1)
    expect(visibles(section, "Candidats").filter(has_text=ip_de(3))).to_have_count(0)


def test_filtre_sans_correspondance_le_dit(section: Locator):
    filtrer(section, "ff:ff")

    expect(section.get_by_text("Aucun Candidat ne correspond à ce filtre.")).to_be_visible()
    expect(section.get_by_role("table", name="Candidats")).to_have_count(0)


def test_filtre_vide_montre_tous_les_candidats(section: Locator):
    filtrer(section, "00:02")
    attendre_seulement(section, "Candidats", 2)

    filtrer(section, "")

    for numero in (2, 3):
        expect(visibles(section, "Candidats").filter(has_text=ip_de(numero))).to_have_count(1)
    expect(visibles(section, "Déjà configurées").filter(has_text=ip_de(1))).to_have_count(1)


def test_filtre_aligne_sur_les_octets(section: Locator):
    # « 2a » n'existe dans 02:a6:… qu'à cheval sur deux octets.
    filtrer(section, "2a")

    expect(section.get_by_text("Aucun Candidat ne correspond à ce filtre.")).to_be_visible()


def test_filtre_invalide_le_dit(section: Locator):
    filtrer(section, "02:zz")

    expect(section.get_by_text(re.compile(r"^MAC invalide"))).to_be_visible()
    expect(section.get_by_role("table", name="Candidats")).to_have_count(0)
