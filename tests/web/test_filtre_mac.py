"""Filtre par MAC des Candidats, tapée telle qu'écrite sur l'étiquette, de bout en bout dans Chromium.

`camera-simulee-1` est configurée (« Déjà configurées »), `-2` est un nouveau Candidat, `-3` perd sa MAC
comme derrière un routeur (test_mac.sans_mac).
"""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import MACS_SIMULEES
from test_administration import administration, api, noms  # noqa: F401 (fixtures)
from test_detection import candidats, onglet, ouvrir_detection, tableau
from test_mac import ip_de, sans_mac


@pytest.fixture
def boite(administration: Page, api, noms) -> Locator:
    assert api.post("/api/essai", json={"ip": ip_de(1), "port": 554}, timeout=30).json()["issue"] == "flux_trouve"
    assert api.post("/api/essai/camera", json={"nom": noms()}).status_code == 201
    sans_mac(administration, "/api/detection", ip_de(3))
    boite = ouvrir_detection(administration)
    candidats(boite)
    return boite


def visibles(boite: Locator, nom: str) -> Locator:
    return tableau(boite, nom).get_by_role("row")


def filtrer(boite: Locator, saisie: str) -> None:
    boite.get_by_role("textbox", name="Filtrer par MAC").fill(saisie)


def attendre_seulement(boite: Locator, nom: str, numero: int) -> None:
    rangees = visibles(boite, nom)
    expect(rangees.filter(has_text=ip_de(numero))).to_have_count(1)
    for autre in {1, 2, 3} - {numero}:
        expect(rangees.filter(has_text=ip_de(autre))).to_have_count(0)


def sans_correspondance(boite: Locator) -> Locator:
    return boite.get_by_role("tabpanel").get_by_text("Aucun Candidat ne correspond à ce filtre.")


@pytest.mark.parametrize(
    "saisie",
    [MACS_SIMULEES[2], MACS_SIMULEES[2].upper().replace(":", "-"), "02a6.0500.0002", " 02A605000002 "],
)
def test_filtre_par_mac_complete_dans_plusieurs_formats(boite: Locator, saisie: str):
    filtrer(boite, saisie)

    attendre_seulement(boite, "Candidats", 2)
    expect(onglet(boite, "Déjà configurées")).to_have_text("Déjà configurées (0)")
    expect(onglet(boite, "Candidats")).to_have_text("Candidats (1)")


@pytest.mark.parametrize("saisie", ["00:01", "0-01", "0001"])
def test_filtre_par_mac_partielle_dans_deja_configurees(boite: Locator, saisie: str):
    filtrer(boite, saisie)

    expect(onglet(boite, "Candidats")).to_have_text("Candidats (0)")
    expect(sans_correspondance(boite)).to_be_visible()
    attendre_seulement(boite, "Déjà configurées", 1)


def test_candidat_sans_mac_masque_des_qu_un_filtre_est_saisi(boite: Locator):
    filtrer(boite, "02:A6")

    expect(visibles(boite, "Candidats").filter(has_text=ip_de(2))).to_have_count(1)
    expect(visibles(boite, "Candidats").filter(has_text=ip_de(3))).to_have_count(0)


def test_filtre_sans_correspondance_le_dit_dans_chaque_onglet(boite: Locator):
    filtrer(boite, "ff:ff")

    expect(sans_correspondance(boite)).to_be_visible()
    expect(boite.get_by_role("table", name="Candidats", exact=True)).to_have_count(0)
    onglet(boite, "Déjà configurées").click()
    expect(sans_correspondance(boite)).to_be_visible()
    expect(boite.get_by_role("table", name="Déjà configurées", exact=True)).to_have_count(0)


def test_filtre_vide_montre_tous_les_candidats(boite: Locator):
    filtrer(boite, "00:02")
    attendre_seulement(boite, "Candidats", 2)

    filtrer(boite, "")

    for numero in (2, 3):
        expect(visibles(boite, "Candidats").filter(has_text=ip_de(numero))).to_have_count(1)
    expect(visibles(boite, "Déjà configurées").filter(has_text=ip_de(1))).to_have_count(1)


def test_filtre_aligne_sur_les_octets(boite: Locator):
    # « 2a » n'existe dans 02:a6:… qu'à cheval sur deux octets.
    filtrer(boite, "2a")

    expect(sans_correspondance(boite)).to_be_visible()


def test_filtre_invalide_le_dit_sous_le_champ(boite: Locator):
    filtrer(boite, "02:zz")

    champ = boite.get_by_role("textbox", name="Filtrer par MAC")
    expect(champ).to_have_attribute("aria-invalid", "true")
    expect(champ).to_have_accessible_description(re.compile(r"^MAC invalide"))
    expect(boite.get_by_role("table", name="Candidats", exact=True)).to_have_count(0)
