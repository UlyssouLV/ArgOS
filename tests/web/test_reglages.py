"""Réglages de la Caméra dans l'Administration, de bout en bout dans Chromium, sur les Caméras simulées ONVIF.

La 2 répond en ONVIF avec ses identifiants de dev, la 4 sans identifiants, les 1 et 3 pas du tout
(simulation/onvif/README.md). Les simulateurs sont recréés « sortie d'usine » au début du module et après
chaque test qui les modifie.
"""

import re
from datetime import UTC, datetime

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import (
    camera_simulee_4_sans_recreation_de_la_date,
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
    expect(incrustations.get_by_label("Affichage du nom", exact=True)).to_have_value("affichee")
    expect(incrustations.get_by_label("Texte du nom", exact=True)).to_have_value("CAM01")
    expect(incrustations.get_by_label("Position du nom", exact=True)).to_have_value("UpperLeft")
    expect(incrustations.get_by_label("Affichage de la date et heure", exact=True)).to_have_value("affichee")
    expect(incrustations).to_contain_text("yyyy-MM-dd HH:mm:ss")
    expect(incrustations.get_by_label("Position de la date et heure", exact=True)).to_have_value("LowerLeft")
    # L'Horloge reste en lecture seule ; le format de la date ne se règle pas.
    expect(horloge.get_by_role("textbox")).to_have_count(0)
    expect(horloge.get_by_role("combobox")).to_have_count(0)
    expect(incrustations.get_by_role("textbox")).to_have_count(1)

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

    position = reglages.get_by_label("Position du nom", exact=True)
    expect(position).to_have_value("Custom", timeout=DELAI_LECTURE_MS)
    expect(position.locator("option:checked")).to_have_text("position personnalisée")


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


# --- Régler les Incrustations ------------------------------------------------------------------------------------


@pytest.fixture
def remise_en_usine():
    yield
    remettre_onvif_en_usine()


def ouvrir_formulaire(page: Page, api, noms, numero: int) -> tuple[str, Locator]:
    """Caméra créée sur la Caméra simulée `numero`, Réglages ouverts et lus."""
    nom = noms()
    creer(page, api, nom, url_simulee(numero))
    reglages = ouvrir_reglages(page, nom)
    expect(reglages.get_by_label("Texte du nom", exact=True)).to_be_visible(timeout=DELAI_LECTURE_MS)
    return nom, reglages


def statut(reglages: Locator, champ: str) -> Locator:
    return reglages.get_by_role("status", name=f"Statut : {champ}")


def enregistrer(page: Page, reglages: Locator) -> dict:
    """Clique « Enregistrer » ; rend le corps du `PATCH` envoyé à l'API."""
    with page.expect_request(lambda r: r.method == "PATCH" and r.url.endswith("/reglages")) as requete:
        reglages.get_by_role("button", name="Enregistrer").click()
    return requete.value.post_data_json


def test_enregistrer_n_envoie_que_les_champs_modifies_et_montre_leur_statut(
    administration: Page, api, noms, remise_en_usine
):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_disabled()

    reglages.get_by_label("Texte du nom", exact=True).fill("Entrée")
    reglages.get_by_label("Position de la date et heure", exact=True).select_option("UpperRight")
    envoye = enregistrer(administration, reglages)

    assert envoye == {"incrustations": {"nom": {"texte": "Entrée"}, "date_heure": {"position": "UpperRight"}}}
    expect(statut(reglages, "texte du nom")).to_have_text("pris", timeout=DELAI_LECTURE_MS)
    expect(statut(reglages, "position de la date et heure")).to_have_text("pris")
    expect(statut(reglages, "position du nom")).to_have_count(0)
    # Les valeurs d'origine restent visibles jusqu'à la fermeture.
    expect(reglages).to_contain_text("d'origine : CAM01")
    expect(reglages).to_contain_text("d'origine : en bas à gauche")


def test_champ_refuse_par_la_camera(administration: Page, api, noms, remise_en_usine):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)

    # La Caméra simulée refuse un texte de plus de 32 caractères.
    reglages.get_by_label("Texte du nom", exact=True).fill("X" * 33)
    reglages.get_by_label("Position du nom", exact=True).select_option("LowerRight")
    enregistrer(administration, reglages)

    expect(statut(reglages, "texte du nom")).to_have_text("refusé", timeout=DELAI_LECTURE_MS)
    expect(statut(reglages, "position du nom")).to_have_text("pris")


def test_annuler_remet_les_valeurs_d_origine_sans_rien_envoyer(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)
    envois: list[str] = []
    administration.on("request", lambda r: envois.append(r.url) if r.method == "PATCH" else None)

    reglages.get_by_label("Texte du nom", exact=True).fill("Entrée")
    reglages.get_by_label("Position du nom", exact=True).select_option("LowerRight")
    reglages.get_by_role("button", name="Annuler").click()

    expect(reglages.get_by_label("Texte du nom", exact=True)).to_have_value("CAM01")
    expect(reglages.get_by_label("Position du nom", exact=True)).to_have_value("UpperLeft")
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_disabled()
    assert envois == []


def test_reprendre_le_nom_argos(administration: Page, api, noms):
    nom, reglages = ouvrir_formulaire(administration, api, noms, 4)

    reglages.get_by_role("button", name="Reprendre le nom ArgOS").click()

    expect(reglages.get_by_label("Texte du nom", exact=True)).to_have_value(nom)


def test_cacher_apres_confirmation_puis_reafficher(administration: Page, api, noms, remise_en_usine):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    affichage = reglages.get_by_label("Affichage de la date et heure", exact=True)

    affichage.select_option("cachee")

    expect(reglages).to_contain_text("Certaines caméras ne permettent pas de la réafficher ensuite.")
    expect(affichage).to_have_value("affichee")  # rien n'est caché avant confirmation
    reglages.get_by_role("button", name="Cacher la date et heure").click()
    expect(affichage).to_have_value("cachee")
    expect(reglages.get_by_label("Position de la date et heure", exact=True)).to_be_disabled()

    assert enregistrer(administration, reglages) == {"incrustations": {"date_heure": {"affichee": False}}}
    expect(statut(reglages, "affichage de la date et heure")).to_have_text("pris", timeout=DELAI_LECTURE_MS)

    affichage.select_option("affichee")
    envoye = enregistrer(administration, reglages)

    assert envoye == {"incrustations": {"date_heure": {"affichee": True, "position": "LowerLeft"}}}
    expect(statut(reglages, "affichage de la date et heure")).to_have_text("pris", timeout=DELAI_LECTURE_MS)


def test_garder_affichee_annule_la_demande(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)

    reglages.get_by_label("Affichage du nom", exact=True).select_option("cachee")
    reglages.get_by_role("button", name="Garder le nom").click()

    expect(reglages.get_by_label("Affichage du nom", exact=True)).to_have_value("affichee")
    expect(reglages).not_to_contain_text("Certaines caméras ne permettent pas")


@pytest.fixture
def date_cachee_sans_recreation(api):
    """camera-simulee-4 ne sait pas recréer la date et heure, déjà cachée ; « sortie d'usine » ensuite."""
    camera_simulee_4_sans_recreation_de_la_date()
    regler_camera_simulee_4_en_onvif("media", "<trt:DeleteOSD><trt:OSDToken>OSD_2</trt:OSDToken></trt:DeleteOSD>")
    yield
    remettre_onvif_en_usine()


def test_afficher_propose_seulement_si_la_camera_sait_recreer(
    administration: Page, api, noms, date_cachee_sans_recreation
):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)

    affichage = reglages.get_by_label("Affichage de la date et heure", exact=True)
    expect(affichage).to_have_value("cachee")
    expect(affichage.locator("option")).to_have_text(["cachée"])
    # Le nom, lui, peut être recréé.
    expect(reglages.get_by_label("Affichage du nom", exact=True).locator("option")).to_have_text(["affichée", "cachée"])
