"""Appareil déjà connu dans l'Aperçu (même MAC, autre chemin), de bout en bout dans Chromium.

L'autre voie de camera-simulee-1 est déclarée à une adresse où l'IP:port ne la rapproche pas : seule
la MAC la relie à l'Appareil essayé.
"""

from playwright.sync_api import Page, expect

from stack_compose import IPS_SIMULEES
from test_administration import administration, api, noms  # noqa: F401 (fixtures)
from test_ajout_camera import DELAI_APERCU_MS, ajouter_par_ip, sans_essai  # noqa: F401 (fixtures)

IP_SANS_APPAREIL = "172.30.0.99"


def test_avertissement_appareil_deja_connu_et_ajout_permis(administration: Page, api, noms, sans_essai):
    voie = noms("Voie")
    assert api.post("/api/essai", json={"ip": IPS_SIMULEES[1], "port": 554}, timeout=30).json()["issue"] == "flux_trouve"
    camera = api.post("/api/essai/camera", json={"nom": voie}).json()
    autre_voie = f"rtsp://{IP_SANS_APPAREIL}:554/Streaming/Channels/201"
    assert api.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": autre_voie}).status_code == 200
    nom = noms("Ajout")

    ajouter_par_ip(administration, IPS_SIMULEES[1])

    panneau = administration.get_by_role("form", name=f"Ajouter {IPS_SIMULEES[1]}:554")
    expect(panneau.locator("video")).to_be_visible(timeout=DELAI_APERCU_MS)
    expect(panneau.get_by_text(f"Cet appareil porte déjà la Caméra {voie}")).to_be_visible()
    panneau.get_by_label("Nom").fill(nom)
    panneau.get_by_role("button", name="Ajouter la Caméra").click()
    expect(administration.get_by_role("row").filter(has_text=nom)).to_be_visible()
