"""Live dans l'UI, de bout en bout dans Chromium : la vidéo arrive vraiment en WebRTC depuis MediaMTX.

Une Caméra H.265 se lit en HLS (docs/adr/0004-hls-pour-les-flux-h265.md). Que Chromium décode le HEVC
dépend de la machine : les tests H.265 le lui retirent, ou le lui font prétendre puis échouer.

La base n'est jamais effacée. Pour maîtriser l'ordre et le tour des Caméras actives, les Caméras
actives qui ne sont pas au test sont désactivées le temps du test, puis réactivées.
"""

import time

import pytest
from playwright.sync_api import Page, Route, expect

from test_administration import api, noms, unique, url_injoignable, url_simulee  # noqa: F401 (fixtures)
from test_connexion import se_connecter

# Intervalle (10 s) + délai (5 s) de sonde, avec de la marge : le codec d'une Caméra créée est lu par la sonde.
DELAI_CODEC_S = 45
# Au-delà de la nouvelle tentative (5 s) du lecteur.
APRES_NOUVELLE_TENTATIVE_S = 7
NAVIGATEUR_SANS_H265 = "Ce navigateur ne lit pas le H.265"

# Un tour de réconciliation du pont (10 s), démarrage du Flux à la demande et nouvelle tentative (5 s), avec de la marge.
DELAI_VIDEO_MS = 45_000
# Une seconde de vidéo jouée suffit à prouver que les images arrivent.
AVANCE_S = 1

# Recense les connexions WebRTC créées par la page, pour compter celles encore ouvertes.
RECENSER_CONNEXIONS = """
window.__connexions = [];
const Natif = window.RTCPeerConnection;
window.RTCPeerConnection = class extends Natif {
  constructor(...args) {
    super(...args);
    window.__connexions.push(this);
  }
};
"""

# Le navigateur dit ne pas décoder le HEVC.
SANS_HEVC = """
const hevc = (type) => /hvc1|hev1/.test(type);
const isTypeSupported = MediaSource.isTypeSupported.bind(MediaSource);
MediaSource.isTypeSupported = (type) => !hevc(type) && isTypeSupported(type);
const canPlayType = HTMLMediaElement.prototype.canPlayType;
HTMLMediaElement.prototype.canPlayType = function (type) {
  return hevc(type) ? "" : canPlayType.call(this, type);
};
"""

# Le navigateur prétend décoder le HEVC, puis échoue dès qu'on lui donne des images.
HEVC_PRETENDU = """
const hevc = (type) => /hvc1|hev1/.test(type);
const isTypeSupported = MediaSource.isTypeSupported.bind(MediaSource);
MediaSource.isTypeSupported = (type) => hevc(type) || isTypeSupported(type);
const addSourceBuffer = MediaSource.prototype.addSourceBuffer;
MediaSource.prototype.addSourceBuffer = function (type) {
  if (hevc(type)) throw new DOMException("HEVC non décodé", "NotSupportedError");
  return addSourceBuffer.call(this, type);
};
"""


@pytest.fixture
def seules_actives(api):
    """Désactive les Caméras actives existantes le temps du test, puis les réactive."""
    desactivees = [camera["id"] for camera in api.get("/api/cameras").json() if camera["active"]]
    for id_camera in desactivees:
        assert api.patch(f"/api/cameras/{id_camera}", json={"active": False}).status_code == 200
    yield
    for id_camera in desactivees:
        assert api.patch(f"/api/cameras/{id_camera}", json={"active": True}).status_code == 200


@pytest.fixture
def creer(api, noms):
    """Crée une Caméra active ; les Caméras d'un test se suivent par nom dans l'ordre de création."""
    base = unique("Live")
    rang = iter("abcdefghij")

    def _creer(url_rtsp: str, emplacement: str | None = None) -> str:
        nom = noms(f"{base}-{next(rang)}")
        assert api.post(
            "/api/cameras", json={"nom": nom, "url_rtsp": url_rtsp, "emplacement": emplacement}
        ).status_code == 201
        return nom

    return _creer


@pytest.fixture
def requetes_flux(page: Page) -> list[str]:
    """URL des requêtes du lecteur de Flux : négociations WHEP et HLS."""
    urls: list[str] = []
    page.on("request", lambda requete: urls.append(requete.url) if "/flux/" in requete.url else None)
    return urls


def whep(urls: list[str]) -> list[str]:
    return [url for url in urls if url.endswith("/whep")]


def hls(urls: list[str]) -> list[str]:
    return [url for url in urls if "/flux/hls/" in url and ".m3u8" in url]


def attendre_codec(api, nom: str, codec: str) -> None:
    echeance = time.monotonic() + DELAI_CODEC_S
    while next(c["codec"] for c in api.get("/api/cameras").json() if c["nom"] == nom) != codec:
        assert time.monotonic() < echeance, f"{nom} : codec toujours différent de {codec}"
        time.sleep(1)


@pytest.fixture
def en_h265(page: Page):
    """La liste des Caméras donne le codec H265 à une Caméra : une Caméra injoignable n'en a jamais."""

    def _en_h265(nom: str) -> None:
        def retoucher(route: Route) -> None:
            reponse = route.fetch()
            route.fulfill(response=reponse, json=[c | {"codec": "H265"} if c["nom"] == nom else c for c in reponse.json()])

        page.route("**/api/cameras", lambda route: retoucher(route) if route.request.method == "GET" else route.continue_())

    yield _en_h265
    # Le Live relit la liste toutes les 10 s : une lecture peut être en cours à la fermeture de la page.
    page.unroute_all(behavior="ignoreErrors")


@pytest.fixture
def live(page: Page, administrateur) -> Page:
    page.add_init_script(RECENSER_CONNEXIONS)
    page.goto("/live")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Live", exact=True)).to_be_visible()
    return page


def camera_affichee(page: Page):
    return page.get_by_role("heading", level=2)


def attendre_que_la_video_joue(page: Page) -> None:
    page.wait_for_function(
        "() => document.querySelector('video')?.currentTime > 0", timeout=DELAI_VIDEO_MS
    )
    depart = page.evaluate("() => document.querySelector('video').currentTime")
    page.wait_for_function(
        f"() => document.querySelector('video').currentTime > {depart + AVANCE_S}", timeout=DELAI_VIDEO_MS
    )


def connexions_ouvertes(page: Page) -> int:
    return page.evaluate("() => window.__connexions.filter((pc) => pc.signalingState !== 'closed').length")


def test_live_ouvre_la_premiere_camera_active_par_nom_et_la_video_joue(seules_actives, creer, live: Page):
    premiere = creer(url_simulee(1), "Portail")
    creer(url_simulee(2))
    live.reload()

    expect(camera_affichee(live)).to_have_text(premiere)
    expect(live.locator(".live-en-tete")).to_contain_text("Portail")
    attendre_que_la_video_joue(live)


def test_suivant_et_fleche_droite_font_le_tour_des_cameras_actives(seules_actives, creer, live: Page):
    premiere = creer(url_simulee(1))
    seconde = creer(url_simulee(2))
    live.reload()
    expect(camera_affichee(live)).to_have_text(premiere)
    attendre_que_la_video_joue(live)

    live.get_by_role("button", name="Suivant").click()

    expect(camera_affichee(live)).to_have_text(seconde)
    attendre_que_la_video_joue(live)
    assert connexions_ouvertes(live) == 1

    live.keyboard.press("ArrowRight")

    expect(camera_affichee(live)).to_have_text(premiere)
    attendre_que_la_video_joue(live)
    assert connexions_ouvertes(live) == 1


def test_aucune_camera_active_propose_d_aller_dans_administration(seules_actives, live: Page):
    expect(live.get_by_text("Aucune Caméra active")).to_be_visible()

    live.get_by_role("main").get_by_role("link", name="Administration").click()

    expect(live.get_by_role("heading", name="Administration")).to_be_visible()


def test_camera_active_injoignable_affiche_flux_indisponible(seules_actives, creer, live: Page):
    nom = creer(url_injoignable())
    live.reload()

    expect(camera_affichee(live)).to_have_text(nom)
    expect(live.get_by_text("Flux indisponible")).to_be_visible(timeout=DELAI_VIDEO_MS)
    assert connexions_ouvertes(live) <= 1


def test_live_camera_h265_sans_decodage_hevc_affiche_le_message_sans_requete_ni_nouvelle_tentative(
    seules_actives, creer, api, requetes_flux, live: Page
):
    nom = creer(url_simulee(4))
    attendre_codec(api, nom, "H265")
    live.add_init_script(SANS_HEVC)
    live.reload()

    expect(camera_affichee(live)).to_have_text(nom)
    expect(live.get_by_text(NAVIGATEUR_SANS_H265)).to_be_visible()
    time.sleep(APRES_NOUVELLE_TENTATIVE_S)

    expect(live.get_by_text(NAVIGATEUR_SANS_H265)).to_be_visible()
    expect(live.get_by_text("Flux indisponible")).to_be_hidden()
    assert requetes_flux == []
    assert connexions_ouvertes(live) == 0


def test_live_camera_h265_que_le_navigateur_echoue_a_decoder_affiche_le_message_sans_nouvelle_tentative(
    seules_actives, creer, api, requetes_flux, live: Page
):
    nom = creer(url_simulee(4))
    attendre_codec(api, nom, "H265")
    live.add_init_script(HEVC_PRETENDU)
    live.reload()

    expect(live.get_by_text(NAVIGATEUR_SANS_H265)).to_be_visible(timeout=DELAI_VIDEO_MS)
    lues = len(hls(requetes_flux))
    time.sleep(APRES_NOUVELLE_TENTATIVE_S)

    assert lues >= 1
    assert len(hls(requetes_flux)) == lues
    assert whep(requetes_flux) == []
    expect(live.get_by_text("Flux indisponible")).to_be_hidden()


def test_live_camera_h265_injoignable_retente_en_hls_puis_suivant_ferme_le_lecteur_hls(
    seules_actives, creer, en_h265, requetes_flux, live: Page
):
    injoignable = creer(url_injoignable())
    h264 = creer(url_simulee(1))
    en_h265(injoignable)
    live.add_init_script(HEVC_PRETENDU)
    live.reload()

    expect(camera_affichee(live)).to_have_text(injoignable)
    expect(live.get_by_text("Flux indisponible")).to_be_visible(timeout=DELAI_VIDEO_MS)
    time.sleep(APRES_NOUVELLE_TENTATIVE_S)
    assert len(hls(requetes_flux)) >= 2
    assert whep(requetes_flux) == []

    live.get_by_role("button", name="Suivant").click()

    expect(camera_affichee(live)).to_have_text(h264)
    attendre_que_la_video_joue(live)
    lues = len(hls(requetes_flux))
    time.sleep(APRES_NOUVELLE_TENTATIVE_S)
    assert len(hls(requetes_flux)) == lues
    assert connexions_ouvertes(live) == 1


def test_live_d_une_camera_h264_a_une_camera_h265_ferme_la_connexion_webrtc(
    seules_actives, creer, api, requetes_flux, live: Page
):
    h264 = creer(url_simulee(1))
    h265 = creer(url_simulee(4))
    attendre_codec(api, h265, "H265")
    live.add_init_script(SANS_HEVC)
    live.reload()
    expect(camera_affichee(live)).to_have_text(h264)
    attendre_que_la_video_joue(live)
    assert len(whep(requetes_flux)) >= 1

    live.get_by_role("button", name="Suivant").click()

    expect(camera_affichee(live)).to_have_text(h265)
    expect(live.get_by_text(NAVIGATEUR_SANS_H265)).to_be_visible()
    assert connexions_ouvertes(live) == 0
    assert hls(requetes_flux) == []
