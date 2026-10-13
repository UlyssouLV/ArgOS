"""Réglages de la Caméra dans l'Administration, de bout en bout dans Chromium, lus sur les Caméras simulées ONVIF.

La 2 répond en ONVIF avec ses identifiants de dev, la 4 sans identifiants, les 1 et 3 pas du tout
(simulation/onvif/README.md). Les simulateurs sont recréés « sortie d'usine » au début du module.
"""

import re
from datetime import UTC, datetime

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import (
    regler_camera_simulee_4_en_onvif,
    remettre_onvif_en_usine,
    url_camera_simulee,
)
from test_administration import administration, api, creer, ligne, noms, unique, url_simulee  # noqa: F401 (fixtures)

# La recherche du port ONVIF, puis la lecture ; une caméra éteinte se fait attendre.
DELAI_LECTURE_MS = 30_000
# Horloge d'usine des Caméras simulées ONVIF.
USINE = datetime(1999, 12, 31, tzinfo=UTC)
# Aucun conteneur à cette adresse du réseau des Caméras simulées.
IP_SANS_CAMERA = "172.30.0.250"


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


def ouvrir_reglages(page: Page, nom: str) -> Locator:
    ligne(page, nom).get_by_role("button", name="Réglages").click()
    return page.get_by_role("region", name=f"Réglages de {nom}")


def valeur(reglages: Locator, terme: str) -> Locator:
    """Valeur (`dd`) qui suit le terme (`dt`) exact dans les Réglages."""
    dt = reglages.locator("dt").filter(has_text=re.compile(f"^{re.escape(terme)}$"))
    return dt.locator("xpath=following-sibling::dd[1]")


def test_reglages_d_une_camera_active_valeurs_usine_et_ecart(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_simulee(2))

    reglages = ouvrir_reglages(administration, nom)

    horloge = reglages.get_by_role("region", name="Horloge")
    expect(horloge).to_be_visible(timeout=DELAI_LECTURE_MS)
    annees = int((datetime.now(UTC) - USINE).days // 365.25)
    expect(valeur(horloge, "Écart avec le Site")).to_have_text(f"en retard de {annees} ans")
    expect(valeur(horloge, "Date et heure de la caméra (UTC)")).to_contain_text("31/12/1999")
    expect(valeur(horloge, "Fuseau")).to_have_text("AWST-8")
    expect(valeur(horloge, "Serveur de temps (NTP)")).to_have_text("non utilisé (serveur : NTP)")
    incrustations = reglages.get_by_role("region", name="Incrustations")
    expect(valeur(incrustations, "Nom")).to_have_text("CAM01")
    expect(valeur(incrustations, "Position du nom")).to_have_text("en haut à gauche")
    expect(valeur(incrustations, "Date et heure")).to_have_text("affichée")
    expect(valeur(incrustations, "Format")).to_have_text("yyyy-MM-dd HH:mm:ss")
    expect(valeur(incrustations, "Position de la date et heure")).to_have_text("en bas à gauche")
    # Lecture seule.
    expect(reglages.get_by_role("textbox")).to_have_count(0)
    expect(reglages.get_by_role("combobox")).to_have_count(0)

    reglages.get_by_role("button", name="Fermer").click()
    expect(reglages).to_have_count(0)


@pytest.fixture
def nom_hors_d_un_coin():
    regler_camera_simulee_4_en_onvif(
        "media",
        '<trt:SetOSD><trt:OSD token="OSD_1"><tt:VideoSourceConfigurationToken>VideoSourceConfig_1'
        "</tt:VideoSourceConfigurationToken><tt:Type>Text</tt:Type>"
        '<tt:Position><tt:Type>Custom</tt:Type><tt:Pos x="0.2" y="-0.5"/></tt:Position>'
        "<tt:TextString><tt:Type>Plain</tt:Type><tt:PlainText>CAM01</tt:PlainText></tt:TextString>"
        "</trt:OSD></trt:SetOSD>",
    )
    yield
    remettre_onvif_en_usine()


def test_position_personnalisee(administration: Page, api, noms, nom_hors_d_un_coin):
    nom = noms()
    creer(administration, api, nom, url_simulee(4))

    reglages = ouvrir_reglages(administration, nom)

    incrustations = reglages.get_by_role("region", name="Incrustations")
    expect(valeur(incrustations, "Position du nom")).to_have_text("position personnalisée", timeout=DELAI_LECTURE_MS)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (lambda: url_simulee(1), "Cette caméra ne répond pas en ONVIF"),
        (
            lambda: url_camera_simulee(2, unique("ui"), identifiants=False).replace("rtsp://", "rtsp://admin:faux@"),
            "La caméra refuse ces identifiants en ONVIF",
        ),
        (lambda: f"rtsp://{IP_SANS_CAMERA}/{unique('eteinte')}", "Caméra injoignable"),
    ],
    ids=["sans_onvif", "identifiants_refuses", "injoignable"],
)
def test_messages_d_erreur(administration: Page, api, noms, url, message):
    nom = noms()
    creer(administration, api, nom, url())

    reglages = ouvrir_reglages(administration, nom)

    expect(reglages.get_by_role("alert")).to_contain_text(message, timeout=DELAI_LECTURE_MS)
    expect(reglages.get_by_role("region", name="Horloge")).to_have_count(0)


def test_pas_de_reglages_pour_une_camera_desactivee(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_simulee(4))
    expect(ligne(administration, nom).get_by_role("button", name="Réglages")).to_be_visible()

    ligne(administration, nom).get_by_role("button", name="Désactiver").click()

    expect(ligne(administration, nom)).to_contain_text("désactivée")
    expect(ligne(administration, nom).get_by_role("button", name="Réglages")).to_have_count(0)
