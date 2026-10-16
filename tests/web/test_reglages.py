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
    camera_simulee_2_avec_une_autre_cle,
    camera_simulee_2_en_tls_ancien,
    camera_simulee_2_muette_apres_encodage,
    camera_simulee_2_sans_https,
    camera_simulee_4_sans_recreation_de_la_date,
    couper_puis_rendre_le_flux_simule,
    regler_camera_simulee_4_en_onvif,
    remettre_onvif_en_usine,
    url_camera_simulee,
)
from test_administration import administration, api, creer, ligne, noms, unique, url_simulee  # noqa: F401 (fixtures)
from test_live import (  # noqa: F401 (fixtures)
    DELAI_VIDEO_MS,
    HEVC_PRETENDU,
    NAVIGATEUR_SANS_H265,
    RECENSER_CONNEXIONS,
    attendre_codec,
    attendre_que_la_video_joue,
    connexions_ouvertes,
    hls,
    requetes_flux,
    whep,
)

# La recherche du port ONVIF, puis la lecture ; une caméra éteinte se fait attendre.
DELAI_LECTURE_MS = 30_000
# Horloge d'usine des Caméras simulées ONVIF.
USINE = datetime(1999, 12, 31, tzinfo=UTC)
# Aucun conteneur à cette adresse du réseau des Caméras simulées.
IP_SANS_CAMERA = "172.30.0.250"


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


def creer_en_clair_accepte(page: Page, api, nom: str, mot_de_passe: str | None = None) -> None:
    """Caméra sur la Caméra simulée 4 (sans HTTPS), ONVIF en clair déjà accepté par l'API.

    `mot_de_passe` : porté par l'URL, que la 4 ignore.
    """
    url = url_simulee(4)
    if mot_de_passe is not None:
        url = url.replace("rtsp://", f"rtsp://admin:{mot_de_passe}@")
    creer(page, api, nom, url)
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    assert api.put(f"/api/cameras/{camera['id']}/reglages/onvif-en-clair").status_code == 204


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
    # Fuseau qu'ArgOS ne reconnaît pas : montré tel quel.
    fuseau = horloge.get_by_label("Fuseau", exact=True)
    expect(fuseau).to_have_value("AWST-8")
    expect(fuseau.locator("option:checked")).to_have_text("AWST-8")
    expect(valeur(horloge, "Serveur de temps (NTP)")).to_have_text("non utilisé (serveur : NTP)")
    incrustations = reglages.get_by_role("region", name="Incrustations")
    expect(incrustations.get_by_label("Affichage du nom", exact=True)).to_have_value("affichee")
    expect(incrustations.get_by_label("Texte du nom", exact=True)).to_have_value("CAM01")
    expect(incrustations.get_by_label("Position du nom", exact=True)).to_have_value("UpperLeft")
    expect(incrustations.get_by_label("Affichage de la date et heure", exact=True)).to_have_value("affichee")
    expect(incrustations).to_contain_text("yyyy-MM-dd HH:mm:ss")
    expect(incrustations.get_by_label("Position de la date et heure", exact=True)).to_have_value("LowerLeft")
    # De l'Horloge, seul le fuseau se choisit ; le format de la date ne se règle pas.
    expect(horloge.get_by_role("textbox")).to_have_count(0)
    expect(horloge.get_by_role("combobox")).to_have_count(1)
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
    creer_en_clair_accepte(administration, api, nom)

    reglages = ouvrir_reglages(administration, nom)

    position = reglages.get_by_label("Position du nom", exact=True)
    expect(position).to_have_value("Custom", timeout=DELAI_LECTURE_MS)
    expect(position.locator("option:checked")).to_have_text("position personnalisée")


def test_bandeau_chiffre_avec_l_empreinte_courte_et_sa_date(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_simulee(2))

    reglages = ouvrir_reglages(administration, nom)

    bandeau = reglages.get_by_role("region", name="Sécurité de l'échange")
    expect(bandeau).to_contain_text("Échange chiffré", timeout=DELAI_LECTURE_MS)
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    securite = api.get(f"/api/cameras/{camera['id']}/reglages", timeout=30).json()["securite"]
    courte = " ".join(securite["empreinte"][i : i + 4] for i in range(0, 16, 4))
    expect(bandeau).to_contain_text(courte)
    memorisee_le = datetime.fromisoformat(securite["empreinte_memorisee_le"]).astimezone()
    expect(bandeau).to_contain_text(f"mémorisé le {memorisee_le:%d/%m/%Y}")
    expect(bandeau).not_to_contain_text("TLS ancien")


def test_onvif_en_clair_accepte_puis_bandeau_et_retrait(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_simulee(4))

    reglages = ouvrir_reglages(administration, nom)

    accord = reglages.get_by_role("region", name="ONVIF en clair")
    expect(accord.get_by_role("alert")).to_contain_text(
        "ONVIF en clair non accepté", timeout=DELAI_LECTURE_MS
    )
    expect(accord).to_contain_text("mot de passe")
    expect(accord).to_contain_text("en clair sur le réseau des caméras")
    expect(reglages.get_by_role("region", name="Horloge")).to_have_count(0)

    accord.get_by_role("button", name="Régler quand même en clair").click()

    expect(reglages.get_by_role("region", name="Horloge")).to_be_visible(timeout=DELAI_LECTURE_MS)
    bandeau = reglages.get_by_role("region", name="Sécurité de l'échange")
    expect(bandeau).to_contain_text("ONVIF en clair")
    expect(bandeau).not_to_contain_text("Échange chiffré")
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    assert camera["onvif_en_clair_accepte"] is True

    bandeau.get_by_role("button", name="Retirer l'accord ONVIF en clair").click()

    expect(reglages.get_by_role("region", name="ONVIF en clair").get_by_role("alert")).to_contain_text(
        "ONVIF en clair non accepté", timeout=DELAI_LECTURE_MS
    )
    expect(reglages.get_by_role("region", name="Horloge")).to_have_count(0)
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    assert camera["onvif_en_clair_accepte"] is False


def test_pas_de_bandeau_en_clair_en_https(administration: Page, api, noms):
    nom = noms()
    creer(administration, api, nom, url_simulee(2))

    reglages = ouvrir_reglages(administration, nom)

    expect(reglages.get_by_role("region", name="Horloge")).to_be_visible(timeout=DELAI_LECTURE_MS)
    expect(reglages.get_by_text("ONVIF en clair")).to_have_count(0)
    expect(reglages.get_by_text("Mot de passe court")).to_have_count(0)


def test_mot_de_passe_court_rappele_en_clair(administration: Page, api, noms):
    nom = noms()
    creer_en_clair_accepte(administration, api, nom, mot_de_passe="court")

    reglages = ouvrir_reglages(administration, nom)

    bandeau = reglages.get_by_role("region", name="Sécurité de l'échange")
    expect(bandeau).to_contain_text("ONVIF en clair", timeout=DELAI_LECTURE_MS)
    expect(bandeau).to_contain_text("Mot de passe court")
    expect(bandeau).to_contain_text("moins de 12 caractères")
    expect(bandeau).to_contain_text("hors ligne")


def test_pas_de_rappel_en_clair_avec_un_mot_de_passe_de_12_caracteres(administration: Page, api, noms):
    nom = noms()
    creer_en_clair_accepte(administration, api, nom, mot_de_passe="x" * 12)

    reglages = ouvrir_reglages(administration, nom)

    bandeau = reglages.get_by_role("region", name="Sécurité de l'échange")
    expect(bandeau).to_contain_text("ONVIF en clair", timeout=DELAI_LECTURE_MS)
    expect(bandeau).not_to_contain_text("Mot de passe court")


@pytest.fixture
def tls_ancien():
    camera_simulee_2_en_tls_ancien()
    yield
    remettre_onvif_en_usine()


def test_tls_ancien_signale(administration: Page, api, noms, tls_ancien):
    nom = noms()
    creer(administration, api, nom, url_simulee(2))

    reglages = ouvrir_reglages(administration, nom)

    bandeau = reglages.get_by_role("region", name="Sécurité de l'échange")
    expect(bandeau).to_contain_text("TLS ancien", timeout=DELAI_LECTURE_MS)


def groupee(empreinte: str) -> str:
    return " ".join(empreinte[i : i + 4] for i in range(0, len(empreinte), 4))


@pytest.fixture
def camera_2_lue_en_https(administration: Page, api, noms) -> tuple[str, dict]:
    """Caméra simulée 2 créée et lue une fois en HTTPS par l'API : sa clé est mémorisée."""
    nom = noms()
    creer(administration, api, nom, url_simulee(2))
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    securite = api.get(f"/api/cameras/{camera['id']}/reglages", timeout=30).json()["securite"]
    return nom, securite


@pytest.fixture
def autre_cle():
    camera_simulee_2_avec_une_autre_cle()
    yield
    remettre_onvif_en_usine()


@pytest.fixture
def sans_https():
    camera_simulee_2_sans_https()
    yield
    remettre_onvif_en_usine()


def test_certificat_change_montre_les_deux_empreintes_puis_confiance_confirmee(
    administration: Page, camera_2_lue_en_https, autre_cle
):
    nom, securite = camera_2_lue_en_https

    reglages = ouvrir_reglages(administration, nom)

    refus = reglages.get_by_role("region", name="Certificat changé")
    expect(refus.get_by_role("alert")).to_contain_text(
        "Le certificat de cette caméra a changé", timeout=DELAI_LECTURE_MS
    )
    expect(valeur(refus, "Certificat mémorisé")).to_contain_text(groupee(securite["empreinte"]))
    memorisee_le = datetime.fromisoformat(securite["empreinte_memorisee_le"]).astimezone()
    expect(valeur(refus, "Certificat mémorisé")).to_contain_text(f"le {memorisee_le:%d/%m/%Y}")
    presente = valeur(refus, "Certificat présenté")
    expect(presente).not_to_contain_text(groupee(securite["empreinte"]))
    expect(refus).to_contain_text("remise en usine")
    expect(refus).to_contain_text("nouveau firmware")
    expect(refus).to_contain_text("autre appareil à cette adresse")
    expect(reglages.get_by_role("region", name="Horloge")).to_have_count(0)

    refus.get_by_role("button", name="Faire confiance au nouveau certificat").click()
    refus.get_by_role("button", name="Annuler").click()
    expect(refus.get_by_role("button", name="Confirmer la confiance")).to_have_count(0)
    refus.get_by_role("button", name="Faire confiance au nouveau certificat").click()
    refus.get_by_role("button", name="Confirmer la confiance").click()

    expect(reglages.get_by_role("region", name="Horloge")).to_be_visible(timeout=DELAI_LECTURE_MS)
    bandeau = reglages.get_by_role("region", name="Sécurité de l'échange")
    expect(bandeau).to_contain_text("Échange chiffré")
    expect(bandeau).not_to_contain_text(groupee(securite["empreinte"][:16]))
    expect(reglages.get_by_role("region", name="Certificat changé")).to_have_count(0)


def test_https_indisponible_puis_oublier_le_certificat(administration: Page, api, camera_2_lue_en_https, sans_https):
    nom, _ = camera_2_lue_en_https

    reglages = ouvrir_reglages(administration, nom)

    refus = reglages.get_by_role("region", name="HTTPS indisponible")
    expect(refus.get_by_role("alert")).to_contain_text("ne répond plus en HTTPS", timeout=DELAI_LECTURE_MS)
    expect(reglages.get_by_role("region", name="Horloge")).to_have_count(0)

    refus.get_by_role("button", name="Oublier le certificat de cette caméra").click()

    expect(reglages.get_by_role("region", name="HTTPS indisponible")).to_have_count(0, timeout=DELAI_LECTURE_MS)
    (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
    assert camera["schema_onvif"] != "https"


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
    if numero == 4:
        creer_en_clair_accepte(page, api, nom)
    else:
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
    expect(statut(reglages, "texte du nom")).to_have_text(
        "pris (demandé : Entrée, relu : Entrée)", timeout=DELAI_LECTURE_MS
    )
    expect(statut(reglages, "position de la date et heure")).to_have_text(
        "pris (demandé : en haut à droite, relu : en haut à droite)"
    )
    expect(statut(reglages, "position du nom")).to_have_count(0)
    # Les valeurs d'origine restent visibles jusqu'à la fermeture.
    expect(reglages).to_contain_text("d'origine : CAM01")
    expect(reglages).to_contain_text("d'origine : en bas à gauche")

    # « Annuler » revient aux valeurs d'origine : les statuts de l'envoi ne s'y appliquent plus.
    reglages.get_by_role("button", name="Annuler").click()
    expect(reglages.get_by_role("status")).to_have_count(0)


def test_champ_refuse_par_la_camera(administration: Page, api, noms, remise_en_usine):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)

    # La Caméra simulée refuse un texte de plus de 32 caractères.
    reglages.get_by_label("Texte du nom", exact=True).fill("X" * 33)
    reglages.get_by_label("Position du nom", exact=True).select_option("LowerRight")
    enregistrer(administration, reglages)

    expect(statut(reglages, "texte du nom")).to_have_text(
        f"refusé (demandé : {'X' * 33}, relu : CAM01)", timeout=DELAI_LECTURE_MS
    )
    expect(statut(reglages, "position du nom")).to_have_text("pris (demandé : en bas à droite, relu : en bas à droite)")


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
    expect(statut(reglages, "affichage de la date et heure")).to_have_text(
        "pris (demandé : cachée, relu : cachée)", timeout=DELAI_LECTURE_MS
    )

    affichage.select_option("affichee")
    envoye = enregistrer(administration, reglages)

    assert envoye == {"incrustations": {"date_heure": {"affichee": True, "position": "LowerLeft"}}}
    expect(statut(reglages, "affichage de la date et heure")).to_have_text(
        "pris (demandé : affichée, relu : affichée)", timeout=DELAI_LECTURE_MS
    )


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


# --- Régler l'Horloge --------------------------------------------------------------------------------------------


def test_fuseau_choisi_dans_la_liste_envoye_seul_et_pris(administration: Page, api, noms, remise_en_usine):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    fuseau = reglages.get_by_label("Fuseau", exact=True)
    expect(fuseau.locator("option").nth(1)).to_have_text("Europe/Paris")

    fuseau.select_option("Europe/Paris")
    envoye = enregistrer(administration, reglages)

    assert envoye == {"horloge": {"fuseau": "Europe/Paris"}, "incrustations": {}}
    # Relu tel que la caméra le garde, en POSIX.
    expect(statut(reglages, "fuseau")).to_have_text(
        "pris (demandé : Europe/Paris, relu : CET-1CEST,M3.5.0,M10.5.0/3)", timeout=DELAI_LECTURE_MS
    )
    expect(reglages).to_contain_text("d'origine : AWST-8")
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_disabled()


def test_fuseau_inconnu_montre_tant_qu_il_n_est_pas_change(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)
    fuseau = reglages.get_by_label("Fuseau", exact=True)

    fuseau.select_option("UTC")

    expect(fuseau.locator("option", has_text="AWST-8")).to_have_count(0)
    reglages.get_by_role("button", name="Annuler").click()
    expect(fuseau).to_have_value("AWST-8")


def test_mettre_a_l_heure_du_site_rafraichit_l_ecart(administration: Page, api, noms, remise_en_usine):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    horloge = reglages.get_by_role("region", name="Horloge")
    expect(valeur(horloge, "Écart avec le Site")).to_contain_text("ans")

    with administration.expect_request(lambda r: r.method == "POST" and r.url.endswith("/mise-a-l-heure")):
        horloge.get_by_role("button", name="Mettre à l'heure du Site").click()

    # Quelques secondes au plus : requêtes, secondes tronquées.
    ecart = re.compile(r"^(à l'heure|en (retard|avance) de \d s)$")
    expect(valeur(horloge, "Écart avec le Site")).to_have_text(ecart, timeout=DELAI_LECTURE_MS)
    expect(horloge.get_by_role("status", name="Statut : mise à l'heure")).to_contain_text("écart relu")
    expect(horloge.get_by_label("Fuseau", exact=True)).to_have_value("AWST-8")
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_disabled()


@pytest.fixture
def camera_4_en_ntp():
    regler_camera_simulee_4_en_onvif(
        "device",
        "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
        "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>",
    )
    yield
    remettre_onvif_en_usine()


def test_mise_a_l_heure_confirmee_quand_la_camera_est_en_ntp(administration: Page, api, noms, camera_4_en_ntp):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)
    horloge = reglages.get_by_role("region", name="Horloge")
    envois: list[str] = []
    # Seulement l'API : le lecteur du Flux, en tête du panneau, fait lui aussi des `POST` (WHEP).
    administration.on("request", lambda r: envois.append(r.url) if r.method == "POST" and "/api/" in r.url else None)
    avertissement = (
        "La caméra se règle sur le serveur de temps NTP. La mettre à l'heure du Site coupe cette synchronisation."
    )

    horloge.get_by_role("button", name="Mettre à l'heure du Site").click()
    expect(horloge).to_contain_text(avertissement)
    horloge.get_by_role("button", name="Garder le serveur de temps").click()

    expect(horloge).not_to_contain_text(avertissement)
    assert envois == []

    horloge.get_by_role("button", name="Mettre à l'heure du Site").click()
    horloge.get_by_role("button", name="Mettre à l'heure quand même").click()

    expect(valeur(horloge, "Serveur de temps (NTP)")).to_have_text(
        "non utilisé (serveur : NTP)", timeout=DELAI_LECTURE_MS
    )
    expect(valeur(horloge, "Écart avec le Site")).not_to_contain_text("ans")


# --- Image ------------------------------------------------------------------------------------------------------


def image(reglages: Locator) -> Locator:
    return reglages.get_by_role("region", name="Image")


def test_image_usine_curseurs_bornes_et_valeurs_d_origine(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    section = image(reglages)

    expect(section).to_contain_text("Partagée par les Caméras de cet Appareil")
    infrarouge = section.get_by_label("Filtre infrarouge", exact=True)
    expect(infrarouge).to_have_value("AUTO")
    expect(infrarouge.locator("option")).to_have_text(["jour", "nuit", "automatique"])
    for libelle in ("Luminosité", "Contraste", "Saturation", "Netteté", "Niveau du WDR"):
        curseur = section.get_by_label(libelle, exact=True)
        expect(curseur).to_have_attribute("type", "range")
        expect(curseur).to_have_attribute("min", "0")
        expect(curseur).to_have_attribute("max", "100")
        expect(curseur).to_have_value("50")
    expect(section.get_by_label("Contre-jour", exact=True)).to_have_value("OFF")
    expect(section.get_by_label("WDR", exact=True)).to_have_value("OFF")
    # La simulée 2 ne borne pas le niveau du contre-jour : non proposé.
    expect(section.get_by_label("Niveau du contre-jour", exact=True)).to_have_count(0)
    expect(section).to_contain_text("d'origine : automatique")
    expect(section).to_contain_text("d'origine : 50")


def test_image_enregistree_statuts_pris_et_wdr_pas_pris(administration: Page, api, noms, remise_en_usine):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    section = image(reglages)

    section.get_by_label("Filtre infrarouge", exact=True).select_option("OFF")
    section.get_by_label("Luminosité", exact=True).fill("70")
    expect(section.locator(".valeur-curseur").first).to_have_text("70")
    section.get_by_label("Contre-jour", exact=True).select_option("ON")
    section.get_by_label("WDR", exact=True).select_option("ON")
    envoye = enregistrer(administration, reglages)

    assert envoye == {
        "incrustations": {},
        "image": {"infrarouge": "OFF", "luminosite": 70, "contre_jour": "ON", "wdr": "ON"},
    }
    expect(statut(reglages, "filtre infrarouge")).to_have_text(
        "pris (demandé : nuit, relu : nuit)", timeout=DELAI_LECTURE_MS
    )
    expect(statut(reglages, "luminosité")).to_have_text("pris (demandé : 70, relu : 70)")
    expect(statut(reglages, "contre-jour")).to_have_text("pris (demandé : activé, relu : activé)")
    expect(statut(reglages, "wdr")).to_have_text("pas pris (demandé : activé, relu : coupé)")
    expect(statut(reglages, "contraste")).to_have_count(0)


def test_image_annuler_sans_rien_envoyer(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)
    section = image(reglages)
    envois: list[str] = []
    administration.on("request", lambda r: envois.append(r.url) if r.method == "PATCH" else None)

    section.get_by_label("Luminosité", exact=True).fill("20")
    section.get_by_label("Filtre infrarouge", exact=True).select_option("ON")
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_enabled()
    reglages.get_by_role("button", name="Annuler").click()

    expect(section.get_by_label("Luminosité", exact=True)).to_have_value("50")
    expect(section.get_by_label("Filtre infrarouge", exact=True)).to_have_value("AUTO")
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_disabled()
    assert envois == []


def test_image_non_reglable_sans_service_image_le_reste_reglable(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 4)

    section = image(reglages)
    expect(section).to_contain_text("Image non réglable sur cette caméra")
    expect(section.get_by_role("slider")).to_have_count(0)
    expect(reglages.get_by_label("Texte du nom", exact=True)).to_be_enabled()
    expect(reglages.get_by_role("region", name="Horloge")).to_be_visible()


# --- Encodage du Flux -------------------------------------------------------------------------------------------

# Chemins des profils des Caméras simulées : une Caméra créée sur l'un d'eux règle son Encodage. Le port RTSP
# (`:554`), ignoré par la correspondance, distingue ces URL de celles des autres tests.
URL_DU_PROFIL = {
    2: "rtsp://admin:argos-simulee@camera-simulee-2:554/cam/realmonitor?channel=1&subtype=0",
    4: "rtsp://camera-simulee-4:554/Streaming/Channels/101",
}
COUPURE = "Le Flux de cette Caméra sera coupé quelques secondes."
# Relecture après un envoi d'Encodage : jusqu'à 20 s, plus la lecture et l'envoi.
DELAI_ENCODAGE_MS = 60_000


def encodage(reglages: Locator) -> Locator:
    return reglages.get_by_role("region", name="Encodage du Flux")


def ouvrir_sur_le_profil(page: Page, api, noms, numero: int) -> Locator:
    """Caméra créée sur le flux principal de la Caméra simulée `numero`, Réglages ouverts et lus."""
    nom = noms()
    creer(page, api, nom, URL_DU_PROFIL[numero])
    if numero == 4:
        (camera,) = [c for c in api.get("/api/cameras").json() if c["nom"] == nom]
        assert api.put(f"/api/cameras/{camera['id']}/reglages/onvif-en-clair").status_code == 204
    reglages = ouvrir_reglages(page, nom)
    expect(reglages.get_by_label("Texte du nom", exact=True)).to_be_visible(timeout=DELAI_LECTURE_MS)
    return reglages


def test_encodage_usine_champs_bornes_et_lecture_seule(administration: Page, api, noms):
    section = encodage(ouvrir_sur_le_profil(administration, api, noms, 2))

    expect(valeur(section, "Profil")).to_have_text("mainStream")
    resolution = section.get_by_label("Résolution", exact=True)
    expect(resolution).to_have_value("2304x1296")
    expect(resolution.locator("option")).to_have_text(["2304×1296", "1920×1080", "1280×720"])
    images = section.get_by_label("Images par seconde", exact=True)
    expect(images).to_have_attribute("type", "number")
    expect(images).to_have_attribute("min", "1")
    expect(images).to_have_attribute("max", "22")
    expect(images).to_have_value("20")
    debit = section.get_by_label("Débit max (kbit/s)", exact=True)
    expect(debit).to_have_attribute("min", "512")
    expect(debit).to_have_attribute("max", "8192")
    expect(debit).to_have_value("4096")
    expect(valeur(section, "Codec")).to_have_text("H264")
    expect(valeur(section, "Qualité")).to_have_text("4")
    expect(valeur(section, "Intervalle entre images clés")).to_have_text("40")
    expect(section).to_contain_text("d'origine : 2304×1296")


def test_hors_bornes_enregistrer_desactive(administration: Page, api, noms):
    reglages = ouvrir_sur_le_profil(administration, api, noms, 2)

    encodage(reglages).get_by_label("Images par seconde", exact=True).fill("25")

    expect(encodage(reglages)).to_contain_text("hors des bornes de la caméra")
    expect(reglages.get_by_role("button", name="Enregistrer")).to_be_disabled()


def test_encodage_confirme_avant_envoi_puis_statuts_pris(administration: Page, api, noms, remise_en_usine):
    reglages = ouvrir_sur_le_profil(administration, api, noms, 2)
    section = encodage(reglages)
    envois: list[str] = []
    administration.on("request", lambda r: envois.append(r.url) if r.method == "PATCH" else None)

    section.get_by_label("Résolution", exact=True).select_option("1920x1080")
    section.get_by_label("Débit max (kbit/s)", exact=True).fill("2048")
    reglages.get_by_role("button", name="Enregistrer").click()

    expect(reglages).to_contain_text(COUPURE)
    assert envois == []
    with administration.expect_request(lambda r: r.method == "PATCH") as requete:
        reglages.get_by_role("button", name="Couper le Flux et enregistrer").click()
    assert requete.value.post_data_json == {
        "incrustations": {},
        "encodage": {"resolution": "1920x1080", "debit_max": 2048},
    }
    expect(statut(reglages, "résolution")).to_have_text(
        "pris (demandé : 1920×1080, relu : 1920×1080)", timeout=DELAI_ENCODAGE_MS
    )
    expect(statut(reglages, "débit max")).to_have_text("pris (demandé : 2048, relu : 2048)")
    expect(statut(reglages, "images par seconde")).to_have_count(0)
    expect(reglages).not_to_contain_text(COUPURE)


def test_ne_pas_couper_le_flux_n_envoie_rien(administration: Page, api, noms):
    reglages = ouvrir_sur_le_profil(administration, api, noms, 2)
    envois: list[str] = []
    administration.on("request", lambda r: envois.append(r.url) if r.method == "PATCH" else None)

    encodage(reglages).get_by_label("Images par seconde", exact=True).fill("15")
    reglages.get_by_role("button", name="Enregistrer").click()
    reglages.get_by_role("button", name="Garder le Flux").click()

    expect(reglages).not_to_contain_text(COUPURE)
    expect(encodage(reglages).get_by_label("Images par seconde", exact=True)).to_have_value("15")
    assert envois == []


def test_image_seule_envoyee_sans_confirmation(administration: Page, api, noms, remise_en_usine):
    reglages = ouvrir_sur_le_profil(administration, api, noms, 2)

    image(reglages).get_by_label("Luminosité", exact=True).fill("60")
    envoye = enregistrer(administration, reglages)

    assert envoye == {"incrustations": {}, "image": {"luminosite": 60}}
    expect(reglages).not_to_contain_text(COUPURE)


def test_encodage_non_reglable_valeurs_en_lecture_seule(administration: Page, api, noms):
    section = encodage(ouvrir_sur_le_profil(administration, api, noms, 4))

    expect(section).to_contain_text("Vidéo non réglable sur cette caméra")
    expect(valeur(section, "Résolution")).to_have_text("2304×1296")
    expect(valeur(section, "Images par seconde")).to_have_text("20")
    expect(section.get_by_role("spinbutton")).to_have_count(0)
    expect(section.get_by_role("combobox")).to_have_count(0)


def test_profil_introuvable(administration: Page, api, noms):
    _, reglages = ouvrir_formulaire(administration, api, noms, 2)

    expect(encodage(reglages)).to_contain_text("Profil vidéo introuvable pour ce Flux")
    expect(encodage(reglages).get_by_role("spinbutton")).to_have_count(0)


@pytest.fixture
def muette_apres_encodage():
    camera_simulee_2_muette_apres_encodage(120)
    yield
    remettre_onvif_en_usine()


def test_camera_sans_reponse_apres_l_envoi(administration: Page, api, noms, muette_apres_encodage):
    reglages = ouvrir_sur_le_profil(administration, api, noms, 2)

    encodage(reglages).get_by_label("Images par seconde", exact=True).fill("15")
    reglages.get_by_role("button", name="Enregistrer").click()
    reglages.get_by_role("button", name="Couper le Flux et enregistrer").click()

    expect(statut(reglages, "images par seconde")).to_have_text(
        "pas pris — la caméra n'a pas répondu après l'envoi", timeout=DELAI_ENCODAGE_MS
    )


# --- Lecteur du Flux ---------------------------------------------------------------------------------------------


@pytest.fixture
def connexions_recensees(administration: Page) -> Page:
    """Administration rechargée avec le recensement des connexions WebRTC de la page."""
    administration.add_init_script(RECENSER_CONNEXIONS)
    administration.reload()
    return administration


def test_le_flux_se_lit_dans_le_panneau_et_fermer_arrete_la_lecture(connexions_recensees: Page, api, noms):
    nom = noms()
    creer(connexions_recensees, api, nom, url_simulee(1))

    reglages = ouvrir_reglages(connexions_recensees, nom)

    attendre_que_la_video_joue(connexions_recensees)
    assert connexions_ouvertes(connexions_recensees) == 1

    reglages.get_by_role("button", name="Fermer").click()

    expect(reglages).to_have_count(0)
    expect(connexions_recensees.locator("video")).to_have_count(0)
    assert connexions_ouvertes(connexions_recensees) == 0


def test_le_flux_h265_se_lit_en_hls_dans_le_panneau(administration: Page, api, noms, requetes_flux):
    nom = noms()
    creer_en_clair_accepte(administration, api, nom)
    attendre_codec(api, nom, "H265")
    # Le navigateur prétend décoder le HEVC : le lecteur va jusqu'à demander la playlist, sans dépendre de la machine.
    administration.add_init_script(HEVC_PRETENDU)
    administration.reload()

    ouvrir_reglages(administration, nom)

    expect(administration.get_by_text(NAVIGATEUR_SANS_H265)).to_be_visible(timeout=DELAI_VIDEO_MS)
    assert len(hls(requetes_flux)) >= 1
    assert whep(requetes_flux) == []


def test_le_lecteur_reprend_seul_apres_une_coupure_du_flux(connexions_recensees: Page, api, noms):
    nom = noms()
    creer(connexions_recensees, api, nom, url_simulee(1))
    reglages = ouvrir_reglages(connexions_recensees, nom)
    attendre_que_la_video_joue(connexions_recensees)
    # Disparaît si la page se recharge.
    connexions_recensees.evaluate("() => { window.__meme_page = true; }")
    avant = connexions_recensees.evaluate("() => window.__connexions.length")

    couper_puis_rendre_le_flux_simule(1)

    connexions_recensees.wait_for_function(
        f"() => window.__connexions.length > {avant}", timeout=DELAI_VIDEO_MS
    )
    attendre_que_la_video_joue(connexions_recensees)
    assert connexions_recensees.evaluate("() => window.__meme_page") is True
    assert connexions_ouvertes(connexions_recensees) == 1
    expect(reglages).to_be_visible()
