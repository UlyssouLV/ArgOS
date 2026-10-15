"""Un Flux refusé (401 sur /flux/…) renvoie à la connexion, comme un 401 de l'API, de bout en bout dans Chromium.

La session est fermée côté API, comme une déconnexion depuis un autre onglet ou une expiration. L'API ne
répond plus au navigateur ensuite : seul un Flux refusé peut alors ramener l'UI à la connexion.

Que Chromium décode le HEVC dépend de la machine : pour lire en HLS, la Caméra simulée H.264 est annoncée en H.265.
MediaMTX sert aussi son Flux en HLS, que le lecteur demande alors comme pour une Caméra H.265, et le navigateur
dit décoder le HEVC pour que le lecteur le demande : les images reçues, elles, sont en H.264.
Le HLS natif (Safari sur iPhone) est simulé en retirant Media Source Extensions : hls.js n'est alors pas pris.
"""

import re

from playwright.sync_api import Page, Route, expect

from stack_compose import COOKIE_SESSION, adresses_ip, client_du_site
from test_administration import administration, api, noms, unique, url_simulee  # noqa: F401 (fixtures)
from test_ajout_camera import ajouter_par_ip, attendre_la_lecture, sans_essai  # noqa: F401 (fixtures)
from test_live import (  # noqa: F401 (fixtures)
    attendre_que_la_video_joue,
    camera_affichee,
    creer,
    en_h265,
    hls,
    live,
    requetes_flux,
    seules_actives,
    whep,
)

# Une requête de Flux suit de près : LL-HLS recharge sa playlist en continu, « Suivant » négocie aussitôt.
DELAI_RETOUR_MS = 15_000

# Le navigateur dit décoder le HEVC ; le reste est intact.
HEVC_ANNONCE = """
const isTypeSupported = MediaSource.isTypeSupported.bind(MediaSource);
MediaSource.isTypeSupported = (type) => /hvc1|hev1/.test(type) || isTypeSupported(type);
"""

# Safari sur iPhone : pas de Media Source Extensions, la balise vidéo lit le HLS elle-même et dit décoder le HEVC.
HLS_NATIF = """
for (const nom of ["MediaSource", "ManagedMediaSource", "WebKitMediaSource"]) delete window[nom];
const canPlayType = HTMLMediaElement.prototype.canPlayType;
HTMLMediaElement.prototype.canPlayType = function (type) {
  return /hvc1|hev1/.test(type) ? "maybe" : canPlayType.call(this, type);
};
"""


def fermer_la_session_cote_api(page: Page) -> None:
    page.route("**/api/**", lambda route: route.abort())
    (jeton,) = [cookie["value"] for cookie in page.context.cookies() if cookie["name"] == COOKIE_SESSION]
    with client_du_site() as client:
        client.cookies.set(COOKIE_SESSION, jeton)
        assert client.delete("/api/session").status_code == 204
        assert client.get("/api/session").status_code == 401


def attendre_le_retour_a_la_connexion(page: Page) -> None:
    expect(page).to_have_url(re.compile(r"/connexion$"), timeout=DELAI_RETOUR_MS)
    expect(page.get_by_role("button", name="Se connecter")).to_be_visible()


def test_session_fermee_pendant_un_live_hls_renvoie_a_la_connexion(
    seules_actives, creer, en_h265, requetes_flux, live: Page
):
    nom = creer(url_simulee(1))
    en_h265(nom)
    live.add_init_script(HEVC_ANNONCE)
    live.reload()
    expect(camera_affichee(live)).to_have_text(nom)
    attendre_que_la_video_joue(live)
    assert hls(requetes_flux)
    assert whep(requetes_flux) == []

    fermer_la_session_cote_api(live)

    attendre_le_retour_a_la_connexion(live)


def test_session_fermee_pendant_un_live_hls_natif_renvoie_a_la_connexion(seules_actives, creer, en_h265, live: Page):
    """Le HLS natif ne dit pas au lecteur que le Flux est refusé : l'UI le demande à l'API (GET /api/session)."""
    nom = creer(url_simulee(1))
    en_h265(nom)
    playlists: list[Route] = []
    live.route("**/flux/hls/**", lambda route: playlists.append(route))
    live.add_init_script(HLS_NATIF)
    with live.expect_request("**/flux/hls/**"):
        live.reload()
    expect(camera_affichee(live)).to_have_text(nom)

    fermer_la_session_cote_api(live)
    live.route("**/api/session", lambda route: route.continue_())
    for playlist in playlists:
        playlist.continue_()

    attendre_le_retour_a_la_connexion(live)


def test_session_fermee_puis_camera_suivante_en_webrtc_renvoie_a_la_connexion(
    seules_actives, creer, requetes_flux, live: Page
):
    premiere = creer(url_simulee(1))
    creer(url_simulee(2))
    live.reload()
    expect(camera_affichee(live)).to_have_text(premiere)
    attendre_que_la_video_joue(live)
    fermer_la_session_cote_api(live)

    live.get_by_role("button", name="Suivant").click()

    attendre_le_retour_a_la_connexion(live)
    assert hls(requetes_flux) == []


def test_session_fermee_pendant_l_apercu_hls_d_un_ajout_renvoie_a_la_connexion(
    administration: Page, requetes_flux, sans_essai
):
    (ip,) = adresses_ip("camera-simulee-1")

    def en_h265_essai(route: Route) -> None:
        reponse = route.fetch()
        route.fulfill(response=reponse, json={**reponse.json(), "codec": "H265"})

    administration.add_init_script(HEVC_ANNONCE)
    administration.reload()
    administration.route("**/api/essai", lambda route: en_h265_essai(route) if route.request.method == "POST" else route.continue_())
    ajouter_par_ip(administration, ip)
    panneau = administration.get_by_role("form", name=f"Ajouter {ip}:554")
    attendre_la_lecture(administration, panneau.locator("video"))
    assert hls(requetes_flux)

    fermer_la_session_cote_api(administration)

    attendre_le_retour_a_la_connexion(administration)
