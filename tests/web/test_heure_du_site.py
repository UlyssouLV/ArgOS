"""Page Heure du Site de l'Administration, de bout en bout dans Chromium.

Le réglage d'origine est remis tel quel en base (et transmis à `temps`) après chaque test qui le change. Les Caméras
du tableau sont créées par l'API, puis désactivées et supprimées.
"""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import compose, remettre_onvif_en_usine, url_camera_simulee
from test_administration import administration, api, noms, unique  # noqa: F401 (fixtures)

# Adresse de temps sur le réseau des Caméras simulées (compose.simulation.yaml).
ADRESSE_TEMPS = "172.30.0.10"
# temps relit son réglage toutes les 2 s ; la page relit l'état toutes les 10 s.
DELAI_SOURCE_MS = 60_000
COLONNES = ("heure_source", "heure_serveur_ntp", "fuseau")
# Vérification de toutes les Caméras actives, une caméra muette comprise.
DELAI_VERIFICATION_MS = 60_000


def psql(requete: str) -> str:
    return compose("exec", "-T", "db", "psql", "-U", "argos", "-d", "argos", "-At", "-c", requete).stdout.strip()


@pytest.fixture
def heure_d_origine(api):
    api.get("/api/heure-du-site")
    avant = psql(f"SELECT {', '.join(COLONNES)} FROM reglages_site WHERE id = 1").split("|")
    yield
    valeurs = ", ".join(
        f"{colonne} = {'NULL' if valeur == '' and colonne == 'fuseau' else repr(valeur)}"
        for colonne, valeur in zip(COLONNES, avant)
    )
    psql(f"UPDATE reglages_site SET {valeurs} WHERE id = 1")
    source = "" if avant[0] == "horloge_serveur" else avant[1]
    compose("exec", "-T", "api", "sh", "-c", f"printf '%s\\n' '{source}' > /temps/source")


@pytest.fixture
def heure_du_site(administration: Page) -> Page:
    administration.get_by_role("navigation", name="Réglages du Site").get_by_role("link", name="Heure du Site").click()
    expect(administration).to_have_url(re.compile(r"/administration/heure-du-site$"))
    expect(administration.get_by_role("heading", name="Heure du Site")).to_be_visible()
    return administration


def valeur(page: Page, terme: str) -> Locator:
    etat = page.get_by_label("Heure du Site", exact=True).locator("div")
    return etat.filter(has=page.get_by_role("term").filter(has_text=re.compile(f"^{terme}$"))).get_by_role("definition")


def test_heure_source_fuseau_et_adresse_du_serveur_de_temps(heure_du_site: Page, api):
    lue = api.get("/api/heure-du-site").json()

    expect(valeur(heure_du_site, "Heure actuelle du Site")).to_contain_text(re.compile(r"\d{2}:\d{2}:\d{2}"))
    expect(valeur(heure_du_site, "Source utilisée")).not_to_be_empty()
    expect(valeur(heure_du_site, "Fuseau")).to_contain_text(lue["fuseau"])
    expect(valeur(heure_du_site, "Adresse du Serveur de temps")).to_have_text(ADRESSE_TEMPS)
    reglage = heure_du_site.get_by_role("form", name="Régler l’Heure du Site")
    expect(reglage.get_by_label("Adresse du serveur NTP")).to_have_value(lue["serveur_ntp"])
    expect(reglage.get_by_label("Fuseau du Site")).to_have_value(lue["fuseau"])
    # Rien de changé : rien à enregistrer.
    expect(reglage.get_by_role("button", name="Enregistrer")).to_be_disabled()


def test_horloge_du_serveur_et_fuseau_enregistres(heure_du_site: Page, api, heure_d_origine):
    reglage = heure_du_site.get_by_role("form", name="Régler l’Heure du Site")
    fuseau = "Pacific/Tahiti" if api.get("/api/heure-du-site").json()["fuseau"] != "Pacific/Tahiti" else "Asia/Tokyo"

    reglage.get_by_label("Horloge du serveur").check()
    reglage.get_by_label("Fuseau du Site").select_option(fuseau)
    with heure_du_site.expect_request(lambda r: r.method == "PATCH" and r.url.endswith("/api/heure-du-site")) as envoi:
        reglage.get_by_role("button", name="Enregistrer").click()

    assert envoi.value.post_data_json == {"source": "horloge_serveur", "fuseau": fuseau}
    expect(heure_du_site.get_by_role("status")).to_contain_text("les Caméras actives sont recalées")
    expect(valeur(heure_du_site, "Fuseau")).to_have_text(fuseau)
    expect(valeur(heure_du_site, "Source utilisée")).to_have_text("horloge du serveur", timeout=DELAI_SOURCE_MS)
    expect(reglage.get_by_label("Adresse du serveur NTP")).to_be_disabled()


def test_serveur_ntp_injoignable_repli_sur_l_horloge_du_serveur(heure_du_site: Page, heure_d_origine):
    reglage = heure_du_site.get_by_role("form", name="Régler l’Heure du Site")

    reglage.get_by_label("Serveur NTP externe").check()
    reglage.get_by_label("Adresse du serveur NTP").fill("192.0.2.1")
    reglage.get_by_role("button", name="Enregistrer").click()

    expect(valeur(heure_du_site, "Source utilisée")).to_have_text(
        "horloge du serveur (repli : 192.0.2.1 injoignable)", timeout=DELAI_SOURCE_MS
    )


def test_adresse_de_serveur_invalide_jamais_envoyee(heure_du_site: Page, api):
    reglage = heure_du_site.get_by_role("form", name="Régler l’Heure du Site")
    envois: list[str] = []
    heure_du_site.on("request", lambda r: envois.append(r.method) if r.url.endswith("/api/heure-du-site") else None)

    reglage.get_by_label("Serveur NTP externe").check()
    reglage.get_by_label("Adresse du serveur NTP").fill("pool.ntp.org iburst")
    reglage.get_by_role("button", name="Enregistrer").click()

    assert reglage.get_by_label("Adresse du serveur NTP").evaluate("champ => !champ.validity.valid")
    assert "PATCH" not in envois


# --- Tableau des Caméras ----------------------------------------------------------------------------------------


@pytest.fixture
def usine():
    remettre_onvif_en_usine()
    yield
    remettre_onvif_en_usine()


def colonnes(ligne: Locator) -> list[Locator]:
    return [ligne.get_by_role("cell").nth(i) for i in range(4)]


def test_tableau_des_cameras_et_verifier_maintenant(administration: Page, api, noms, usine):
    calee_ailleurs, sans_onvif = noms("Heure"), noms("Heure")
    for nom, numero in ((calee_ailleurs, 2), (sans_onvif, 1)):
        reponse = api.post("/api/cameras", json={"nom": nom, "url_rtsp": url_camera_simulee(numero, unique("ui"))})
        assert reponse.status_code == 201, reponse.text
    administration.get_by_role("navigation", name="Réglages du Site").get_by_role("link", name="Heure du Site").click()
    tableau = administration.get_by_role("table", name="Caméras")

    # Vérifiées à l'ajout.
    nom, etat, ecart, verifiee = colonnes(tableau.get_by_role("row").filter(has_text=sans_onvif))
    expect(etat).to_have_text("sans ONVIF")
    expect(ecart).to_have_text("—")
    expect(verifiee).to_contain_text(re.compile(r"\d{2}:\d{2}:\d{2}"))
    expect(colonnes(tableau.get_by_role("row").filter(has_text=calee_ailleurs))[1]).to_have_text(
        re.compile("^(calée|écart|recalée)$")
    )

    # Réglée ailleurs entre-temps : la vérification la recale.
    compose(
        "exec", "-T", "api", "python", "-c",
        "from argos_api import onvif; from datetime import datetime, UTC;"
        "onvif.caler('rtsp://admin:argos-simulee@camera-simulee-2/', onvif.Retenu(), 'ntp.example.org', 'UTC0',"
        " lambda: datetime.now(UTC))",
    )
    with administration.expect_request(
        lambda r: r.method == "POST" and r.url.endswith("/api/heure-du-site/verification"), timeout=DELAI_VERIFICATION_MS
    ):
        administration.get_by_role("button", name="Vérifier maintenant").click()

    _, etat, ecart, _ = colonnes(tableau.get_by_role("row").filter(has_text=calee_ailleurs))
    expect(etat).to_have_text("recalée", timeout=DELAI_VERIFICATION_MS)
    expect(ecart).to_have_text(re.compile(r"^[+−-]\d+,\d s$"))
    expect(administration.get_by_role("button", name="Vérifier maintenant")).to_be_enabled()
