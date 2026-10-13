"""Codec de chaque Caméra dans l'Administration, de bout en bout dans Chromium.

Les Caméras simulées 1 et 4 diffusent en H.264 et en H.265 (compose.simulation.yaml). Aucune ne diffuse un
autre codec : la réponse de l'API est retouchée pour en donner un.
"""

from playwright.sync_api import Page, Route, expect

from test_administration import administration, api, ligne, noms, url_injoignable  # noqa: F401 (fixtures)
from test_ajout_camera import sans_essai  # noqa: F401 (fixture)
from test_mac import cellule, ip_de


def ajouter_depuis_l_essai(api, numero: int, nom: str) -> None:
    assert api.post("/api/essai", json={"ip": ip_de(numero), "port": 554}, timeout=30).json()["issue"] == "flux_trouve"
    assert api.post("/api/essai/camera", json={"nom": nom}).status_code == 201
    api.delete("/api/essai")


def test_colonne_codec_des_cameras(administration: Page, api, noms, sans_essai):
    h264, h265, inconnu, autre = noms("H264"), noms("H265"), noms("Inconnu"), noms("Autre")
    ajouter_depuis_l_essai(api, 1, h264)
    ajouter_depuis_l_essai(api, 4, h265)
    assert api.post("/api/cameras", json={"nom": inconnu, "url_rtsp": url_injoignable()}).status_code == 201
    assert api.post("/api/cameras", json={"nom": autre, "url_rtsp": url_injoignable()}).status_code == 201

    def en_mjpeg(route: Route) -> None:
        reponse = route.fetch()
        cameras = [c | {"codec": "MJPEG"} if c["nom"] == autre else c for c in reponse.json()]
        route.fulfill(response=reponse, json=cameras)

    administration.route("**/api/cameras", lambda route: en_mjpeg(route) if route.request.method == "GET" else route.continue_())
    administration.reload()
    tableau = administration.get_by_role("table").filter(has=administration.get_by_role("columnheader", name="Nom"))

    expect(cellule(tableau, ligne(administration, h264), "Codec")).to_have_text("H.264")
    expect(cellule(tableau, ligne(administration, h265), "Codec")).to_have_text("H.265")
    expect(cellule(tableau, ligne(administration, inconnu), "Codec")).to_have_text("inconnu")
    expect(cellule(tableau, ligne(administration, autre), "Codec")).to_have_text("MJPEG")
