"""Live dans l'UI, de bout en bout dans Chromium : la vidéo arrive vraiment en WebRTC depuis MediaMTX.

La base n'est jamais effacée. Pour maîtriser l'ordre et le tour des Caméras actives, les Caméras
actives qui ne sont pas au test sont désactivées le temps du test, puis réactivées.
"""

import pytest
from playwright.sync_api import Page, expect

from test_administration import api, noms, unique, url_injoignable, url_simulee  # noqa: F401 (fixtures)
from test_connexion import se_connecter

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
    premiere = creer(url_simulee("cam1"), "Portail")
    creer(url_simulee("cam2"))
    live.reload()

    expect(camera_affichee(live)).to_have_text(premiere)
    expect(live.locator(".live-en-tete")).to_contain_text("Portail")
    attendre_que_la_video_joue(live)


def test_suivant_et_fleche_droite_font_le_tour_des_cameras_actives(seules_actives, creer, live: Page):
    premiere = creer(url_simulee("cam1"))
    seconde = creer(url_simulee("cam2"))
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
