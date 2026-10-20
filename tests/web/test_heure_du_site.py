"""Page Heure du Site de l'Administration, de bout en bout dans Chromium.

Le réglage d'origine est remis tel quel en base (et transmis à `temps`) après chaque test qui le change.
"""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from stack_compose import compose
from test_administration import administration, api  # noqa: F401 (fixtures)

# Adresse de temps sur le réseau des Caméras simulées (compose.simulation.yaml).
ADRESSE_TEMPS = "172.30.0.10"
# temps relit son réglage toutes les 2 s ; la page relit l'état toutes les 10 s.
DELAI_SOURCE_MS = 60_000
COLONNES = ("heure_source", "heure_serveur_ntp", "fuseau")


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
