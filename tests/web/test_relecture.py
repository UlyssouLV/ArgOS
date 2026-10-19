"""Relecture sur la page Enregistrement : sélection d'une Caméra, Timeline d'enregistrement, viewer (ADR 0013).

La timeline et le clic se testent sur des Segments simulés (route de l'API), pour maîtriser plages et trous.
La lecture se teste de bout en bout : Caméra simulée qui enregistre, Segments raccourcis à 2 s par l'API de
contrôle du pont, relus par `/flux/relecture/get`.
"""

import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from stack_compose import raccourcir_les_segments
from test_administration import api, noms, url_injoignable, url_simulee  # noqa: F401 (fixtures)
from test_connexion import se_connecter
from test_live import NAVIGATEUR_SANS_H265, SANS_HEVC

CHEMIN_RELECTURE = "/flux/relecture/get"
# Un tour de réconciliation du pont (10 s), avec de la marge.
DELAI_PONT_S = 20
# Deux Segments de 2 s fermés après le démarrage du Flux à la demande, avec de la marge.
DELAI_SEGMENTS_FERMES_S = 60
DELAI_VIDEO_MS = 30_000
# Un rafraîchissement de la Timeline d'enregistrement (10 s), avec de la marge.
DELAI_RAFRAICHISSEMENT_MS = 15_000
SANS_SEGMENT = "Aucun enregistrement sur cette période"
VITESSES = (1, 2, 4, 8, 16)


@pytest.fixture
def enregistrement(page: Page, administrateur) -> Page:
    page.goto("/enregistrement")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Enregistrement")).to_be_visible()
    return page


@pytest.fixture
def relectures(enregistrement: Page) -> list[str]:
    """URL de relecture demandées par la page, dans l'ordre (la vidéo ne passe pas par `page.route`)."""
    demandees: list[str] = []
    enregistrement.on("request", lambda r: demandees.append(r.url) if CHEMIN_RELECTURE in r.url else None)
    return demandees


def _iso(instant: datetime) -> str:
    return instant.isoformat().replace("+00:00", "Z")


def _simuler_segments(page: Page, id_camera: int, fenetre: tuple[datetime, datetime], plages: list[tuple[datetime, datetime]]) -> None:
    corps = {
        "debut": _iso(fenetre[0]),
        "fin": _iso(fenetre[1]),
        "segments": [{"debut": _iso(d), "fin": _iso(f)} for d, f in plages],
    }
    page.route(f"**/api/cameras/{id_camera}/segments", lambda route: route.fulfill(json=corps))


def _camera(api, noms, url: str) -> dict:
    reponse = api.post("/api/cameras", json={"nom": noms(), "url_rtsp": url})
    assert reponse.status_code == 201
    return reponse.json()


def _selectionner(page: Page, nom: str) -> Locator:
    page.reload()
    page.get_by_role("table", name="Débits par Caméra").get_by_role("row").filter(has_text=nom).click()
    relecture = page.get_by_role("region", name=f"Relecture — {nom}")
    expect(relecture).to_be_visible()
    return relecture


def _cliquer_a(timeline: Locator, fraction: float) -> None:
    boite = timeline.bounding_box()
    assert boite is not None
    timeline.click(position={"x": boite["width"] * fraction, "y": boite["height"] / 2})


def _debut_demande(url: str) -> str:
    return parse_qs(urlparse(url).query)["start"][0]


def test_avant_selection_la_page_invite_a_choisir_une_camera(enregistrement: Page):
    expect(enregistrement.get_by_text("Cliquez sur une Caméra du résumé pour relire ses enregistrements.")).to_be_visible()


def test_selectionner_une_camera_montre_sa_timeline_avec_plages_et_trous(enregistrement: Page, api, noms):
    camera = _camera(api, noms, url_injoignable())
    maintenant = datetime.now(UTC)
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    _simuler_segments(
        enregistrement,
        camera["id"],
        fenetre,
        [
            (maintenant - timedelta(minutes=50), maintenant - timedelta(minutes=45)),
            (maintenant - timedelta(minutes=20), maintenant - timedelta(minutes=10)),
        ],
    )

    relecture = _selectionner(enregistrement, camera["nom"])

    timeline = relecture.get_by_role("group", name="Timeline d’enregistrement")
    plages = timeline.locator(".plage-enregistree")
    expect(plages).to_have_count(2)
    boite = timeline.bounding_box()
    premiere, seconde = plages.nth(0).bounding_box(), plages.nth(1).bounding_box()
    assert boite and premiere and seconde
    # 10 min sur 60 commencent après 10 min, 5 min colorées, puis un trou de 25 min avant la seconde plage.
    assert premiere["x"] - boite["x"] == pytest.approx(boite["width"] * 10 / 60, abs=2)
    assert premiere["width"] == pytest.approx(boite["width"] * 5 / 60, abs=2)
    assert seconde["x"] - (premiere["x"] + premiere["width"]) == pytest.approx(boite["width"] * 25 / 60, abs=2)
    expect(relecture.get_by_text(SANS_SEGMENT)).to_have_count(0)
    expect(enregistrement.get_by_role("table", name="Débits par Caméra").get_by_role("row", selected=True)).to_contain_text(camera["nom"])


def test_camera_sans_segment_affiche_un_message(enregistrement: Page, api, noms):
    camera = _camera(api, noms, url_injoignable())

    relecture = _selectionner(enregistrement, camera["nom"])

    expect(relecture.get_by_text(SANS_SEGMENT)).to_be_visible()
    expect(relecture.locator(".plage-enregistree")).to_have_count(0)
    expect(relecture.locator("video")).to_have_count(0)


def test_clic_sur_la_timeline_positionne_le_viewer_au_debut_du_segment(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_injoignable())
    maintenant = datetime.now(UTC)
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    ancien = (maintenant - timedelta(minutes=50), maintenant - timedelta(minutes=45))
    recent = (maintenant - timedelta(minutes=20), maintenant - timedelta(minutes=10))
    _simuler_segments(enregistrement, camera["id"], fenetre, [ancien, recent])
    relecture = _selectionner(enregistrement, camera["nom"])
    timeline = relecture.get_by_role("group", name="Timeline d’enregistrement")

    # Dans le Segment ancien (à 47 min d'ici) : son début, pas l'instant cliqué.
    _cliquer_a(timeline, 13 / 60)
    expect(relecture.locator(".plage-courante")).to_have_count(1)
    _attendre(enregistrement, lambda: len(relectures) >= 1)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == ancien[0]
    assert parse_qs(urlparse(relectures[-1]).query)["path"] == [camera["chemin_flux"]]

    # Dans le trou, plus près du Segment récent (à 30 min d'ici : 10 min de son début, 15 min de la fin de l'ancien).
    _cliquer_a(timeline, 30 / 60)
    _attendre(enregistrement, lambda: len(relectures) >= 2)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == recent[0]


def test_la_timeline_se_rafraichit_et_l_enchainement_attend_le_segment_ferme_ensuite(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_injoignable())
    maintenant = datetime.now(UTC)
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    ancien = (maintenant - timedelta(minutes=3), maintenant - timedelta(minutes=2))
    ferme_ensuite = (maintenant - timedelta(minutes=2), maintenant - timedelta(minutes=1))
    lectures = 0

    def segments(route: Route) -> None:
        nonlocal lectures
        lectures += 1
        plages = [ancien] if lectures == 1 else [ancien, ferme_ensuite]
        route.fulfill(json={
            "debut": _iso(fenetre[0]),
            "fin": _iso(fenetre[1]),
            "segments": [{"debut": _iso(d), "fin": _iso(f)} for d, f in plages],
        })

    enregistrement.route(f"**/api/cameras/{camera['id']}/segments", segments)
    relecture = _selectionner(enregistrement, camera["nom"])
    _cliquer_a(relecture.get_by_role("group", name="Timeline d’enregistrement"), 57.5 / 60)
    _attendre(enregistrement, lambda: len(relectures) >= 1)

    # Fin du dernier Segment connu : le viewer attend le rafraîchissement qui apporte le Segment fermé depuis.
    relecture.locator("video").dispatch_event("ended")
    expect(relecture.locator(".plage-enregistree")).to_have_count(2, timeout=DELAI_RAFRAICHISSEMENT_MS)
    _attendre(enregistrement, lambda: len(relectures) >= 2)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == ferme_ensuite[0]
    expect(relecture.locator(".plage-courante")).to_have_count(1)


def test_camera_h265_sur_un_navigateur_sans_hevc_le_dit_sans_rien_demander(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_injoignable())
    maintenant = datetime.now(UTC)
    _simuler_segments(
        enregistrement,
        camera["id"],
        (maintenant - timedelta(hours=1), maintenant),
        [(maintenant - timedelta(minutes=30), maintenant - timedelta(minutes=29))],
    )

    def en_h265(route: Route) -> None:
        reponse = route.fetch()
        route.fulfill(response=reponse, json=[c | {"codec": "H265"} if c["id"] == camera["id"] else c for c in reponse.json()])

    enregistrement.route("**/api/cameras", en_h265)
    enregistrement.add_init_script(SANS_HEVC)
    relecture = _selectionner(enregistrement, camera["nom"])

    _cliquer_a(relecture.get_by_role("group", name="Timeline d’enregistrement"), 30.5 / 60)

    expect(relecture.get_by_text(NAVIGATEUR_SANS_H265)).to_be_visible()
    expect(relecture.get_by_text("Enregistrement indisponible")).to_have_count(0)
    enregistrement.wait_for_timeout(1000)
    assert relectures == []


def _attendre(page: Page, condition, delai_s: float = 10) -> None:
    """Attend par la page : Playwright (synchrone) ne livre ses événements que pendant ses propres appels."""
    echeance = time.monotonic() + delai_s
    while not condition():
        assert time.monotonic() < echeance, "condition jamais remplie"
        page.wait_for_timeout(100)


def _segments_fermes(api, id_camera: int, combien: int) -> list[dict]:
    echeance = time.monotonic() + DELAI_SEGMENTS_FERMES_S
    while True:
        segments = api.get(f"/api/cameras/{id_camera}/segments").json()["segments"]
        if len(segments) >= combien:
            return segments
        assert time.monotonic() < echeance, f"moins de {combien} Segments fermés après {DELAI_SEGMENTS_FERMES_S} s"
        time.sleep(1)


def _resserrer_la_fenetre(page: Page, id_camera: int) -> None:
    """Fenêtre réduite aux Segments réels : des Segments de 2 s tiennent moins d'un pixel sur une heure."""

    def resserrer(route: Route) -> None:
        reponse = route.fetch()
        corps = reponse.json()
        if corps["segments"]:
            corps["debut"], corps["fin"] = corps["segments"][0]["debut"], corps["segments"][-1]["fin"]
        route.fulfill(response=reponse, json=corps)

    page.route(f"**/api/cameras/{id_camera}/segments", resserrer)


def test_relire_un_segment_play_pause_vitesses_et_enchainement(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_simulee(1))
    assert api.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    raccourcir_les_segments(camera["chemin_flux"], DELAI_PONT_S)
    segments = _segments_fermes(api, camera["id"], 3)
    _resserrer_la_fenetre(enregistrement, camera["id"])
    relecture = _selectionner(enregistrement, camera["nom"])
    video = relecture.locator("video")

    # Au milieu du premier Segment : la vidéo part de son début et joue.
    timeline = relecture.get_by_role("group", name="Timeline d’enregistrement")
    boite, premiere = timeline.bounding_box(), relecture.locator(".plage-enregistree").first.bounding_box()
    assert boite and premiere
    _cliquer_a(timeline, (premiere["x"] - boite["x"] + premiere["width"] / 2) / boite["width"])
    expect(video).to_have_js_property("paused", False, timeout=DELAI_VIDEO_MS)
    _attendre(enregistrement, lambda: video.evaluate("v => v.currentTime") > 0.2, DELAI_VIDEO_MS / 1000)
    assert datetime.fromisoformat(_debut_demande(relectures[0])) == datetime.fromisoformat(segments[0]["debut"])
    expect(relecture.get_by_role("progressbar", name="Progression dans le Segment")).to_be_visible()

    relecture.get_by_role("button", name="Pause").click()
    expect(video).to_have_js_property("paused", True)
    relecture.get_by_role("button", name="Lecture").click()
    expect(video).to_have_js_property("paused", False)

    for vitesse in VITESSES:
        relecture.get_by_role("button", name=f"×{vitesse}", exact=True).click()
        expect(video).to_have_js_property("playbackRate", vitesse)
        expect(relecture.get_by_role("button", name=f"×{vitesse}", exact=True)).to_have_attribute("aria-pressed", "true")

    # À ×16, un Segment de 2 s s'achève vite : le viewer enchaîne sur le suivant, à la même vitesse.
    _attendre(enregistrement, lambda: len(relectures) >= 2, DELAI_VIDEO_MS / 1000)
    assert datetime.fromisoformat(_debut_demande(relectures[1])) == datetime.fromisoformat(segments[1]["debut"])
    expect(video).to_have_js_property("playbackRate", 16)
