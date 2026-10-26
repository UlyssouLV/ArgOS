"""Relecture (`/relecture/<id>`) : Caméra, jour du Site, Timeline d'enregistrement d'un jour, viewer (ADR 0013, 0017).

La timeline et le clic se testent sur des Segments simulés (route de l'API), pour maîtriser plages et trous : le
« jour » simulé y est la dernière heure, sauf pour la durée réelle d'un jour de changement d'heure.
La lecture se teste de bout en bout : Caméra simulée qui enregistre, Segments raccourcis à 2 s par l'API de
contrôle du pont, relus par `/flux/relecture/get`.
"""

import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from stack_compose import raccourcir_les_segments
from test_administration import api, noms, url_injoignable, url_simulee  # noqa: F401 (fixtures)
from test_connexion import rail, se_connecter
from test_live import NAVIGATEUR_SANS_H265, SANS_HEVC

CHEMIN_RELECTURE = "/flux/relecture/get"
# Un tour de réconciliation du pont (10 s), avec de la marge.
DELAI_PONT_S = 20
# Deux Segments de 2 s fermés après le démarrage du Flux à la demande, avec de la marge.
DELAI_SEGMENTS_FERMES_S = 60
DELAI_VIDEO_MS = 30_000
# Un rafraîchissement de la Timeline d'enregistrement (10 s), avec de la marge.
DELAI_RAFRAICHISSEMENT_MS = 15_000
SANS_SEGMENT = "Aucun enregistrement ce jour"
VITESSES = (1, 2, 4, 8, 16)
# Une heure sur la largeur de la Timeline : quelques secondes par pixel.
PRECISION_CLIC_S = 10


@pytest.fixture
def enregistrement(page: Page, administrateur) -> Page:
    """Page connectée ; `_selectionner` y ouvre la Relecture d'une Caméra."""
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


def _maintenant() -> datetime:
    """À la seconde : le navigateur ne garde que les millisecondes des instants qu'il redemande."""
    return datetime.now(UTC).replace(microsecond=0)


def _iso(instant: datetime) -> str:
    return instant.isoformat().replace("+00:00", "Z")


def _corps(
    fenetre: tuple[datetime, datetime],
    plages: list[tuple[datetime, datetime]],
    jour: str = "2026-10-26",
    jours: tuple[str, str] = ("2026-10-25", "2026-10-26"),
    conservation: tuple[datetime, datetime] | None = None,
) -> dict:
    """Réponse de `/segments` : `fenetre` tient lieu de jour (`debut_jour` → `fin_jour`)."""
    conservation = conservation or fenetre
    return {
        "debut": _iso(conservation[0]),
        "fin": _iso(conservation[1]),
        "fuseau": "UTC",
        "premier_jour": jours[0],
        "dernier_jour": jours[1],
        "jour": jour,
        "debut_jour": _iso(fenetre[0]),
        "fin_jour": _iso(fenetre[1]),
        "segments": [{"debut": _iso(d), "fin": _iso(f)} for d, f in plages],
    }


def _simuler_segments(page: Page, id_camera: int, fenetre: tuple[datetime, datetime], plages: list[tuple[datetime, datetime]]) -> None:
    corps = _corps(fenetre, plages)
    page.route(f"**/api/cameras/{id_camera}/segments*", lambda route: route.fulfill(json=corps))


def _camera(api, noms, url: str) -> dict:
    reponse = api.post("/api/cameras", json={"nom": noms(), "url_rtsp": url})
    assert reponse.status_code == 201
    return reponse.json()


def _relecture(page: Page, nom: str) -> Locator:
    relecture = page.get_by_role("region", name=f"Relecture — {nom}")
    expect(relecture).to_be_visible()
    return relecture


def _selectionner(page: Page, nom: str) -> Locator:
    """Depuis le résumé d'Enregistrement, comme l'Administrateur : la ligne de la Caméra ouvre sa Relecture."""
    page.goto("/enregistrement")
    page.get_by_role("table", name="Débits par Caméra").get_by_role("row").filter(has_text=nom).click()
    return _relecture(page, nom)


def _plages(zone: Locator) -> Locator:
    """Plages de la Timeline, celle en lecture comprise."""
    return zone.get_by_role("img", name=re.compile(r"^Plage (enregistrée|lue) "))


def _plage_lue(zone: Locator) -> Locator:
    return zone.get_by_role("img", name=re.compile(r"^Plage lue "))


def _cliquer_a(timeline: Locator, fraction: float) -> None:
    boite = timeline.bounding_box()
    assert boite is not None
    timeline.click(position={"x": boite["width"] * fraction, "y": boite["height"] / 2})


def _debut_demande(url: str) -> str:
    return parse_qs(urlparse(url).query)["start"][0]


def test_une_camera_du_resume_d_enregistrement_ouvre_sa_relecture(enregistrement: Page, api, noms):
    camera = _camera(api, noms, url_injoignable())

    _selectionner(enregistrement, camera["nom"])

    expect(enregistrement).to_have_url(re.compile(rf"/relecture/{camera['id']}$"))
    expect(enregistrement.get_by_role("heading", name="Relecture")).to_be_visible()
    expect(rail(enregistrement).get_by_role("link", name="Relecture")).to_have_attribute("aria-current", "page")
    expect(enregistrement.get_by_role("combobox", name="Caméra")).to_have_value(str(camera["id"]))


def test_relecture_rouvre_la_derniere_camera_relue(enregistrement: Page, api, noms):
    premiere, derniere = _camera(api, noms, url_injoignable()), _camera(api, noms, url_injoignable())
    enregistrement.goto(f"/relecture/{premiere['id']}")
    _relecture(enregistrement, premiere["nom"])
    enregistrement.get_by_role("combobox", name="Caméra").select_option(str(derniere["id"]))
    expect(enregistrement).to_have_url(re.compile(rf"/relecture/{derniere['id']}$"))
    _relecture(enregistrement, derniere["nom"])

    enregistrement.goto("/live")
    rail(enregistrement).get_by_role("link", name="Relecture").click()

    expect(enregistrement).to_have_url(re.compile(rf"/relecture/{derniere['id']}$"))
    _relecture(enregistrement, derniere["nom"])


def test_changer_de_camera_ou_de_jour_recharge_la_timeline(enregistrement: Page, api, noms):
    camera, autre = _camera(api, noms, url_injoignable()), _camera(api, noms, url_injoignable())
    maintenant = datetime.now(UTC)
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    plage = (maintenant - timedelta(minutes=30), maintenant - timedelta(minutes=29))
    demandes: list[tuple[int, str | None]] = []

    def segments(route: Route) -> None:
        url = urlparse(route.request.url)
        id_camera = int(url.path.split("/")[-2])
        jour = parse_qs(url.query).get("jour", [None])[0]
        demandes.append((id_camera, jour))
        # Trois jours dans la Conservation ; une plage le 25 pour `camera`, aucune ailleurs.
        plages = [plage] if (id_camera, jour) == (camera["id"], "2026-10-25") else []
        route.fulfill(json=_corps(fenetre, plages, jour=jour or "2026-10-26", jours=("2026-10-24", "2026-10-26")))

    enregistrement.route("**/api/cameras/*/segments*", segments)
    enregistrement.goto(f"/relecture/{camera['id']}")
    relecture = _relecture(enregistrement, camera["nom"])
    jour = enregistrement.get_by_role("group", name="Jour relu")

    # Jour courant : rien à relire, et pas de jour après celui-ci.
    expect(relecture.get_by_text(SANS_SEGMENT)).to_be_visible()
    expect(jour.get_by_label("Jour", exact=True)).to_have_value("2026-10-26")
    expect(jour.get_by_role("button", name="Jour suivant")).to_be_disabled()

    jour.get_by_role("button", name="Jour précédent").click()
    expect(_plages(relecture)).to_have_count(1)
    expect(jour.get_by_label("Jour", exact=True)).to_have_value("2026-10-25")
    assert demandes[-1] == (camera["id"], "2026-10-25")

    # Premier jour de la Conservation : on ne recule pas plus loin, ni par le champ.
    jour.get_by_role("button", name="Jour précédent").click()
    expect(jour.get_by_label("Jour", exact=True)).to_have_value("2026-10-24")
    expect(jour.get_by_role("button", name="Jour précédent")).to_be_disabled()
    expect(jour.get_by_label("Jour", exact=True)).to_have_attribute("min", "2026-10-24")
    expect(jour.get_by_label("Jour", exact=True)).to_have_attribute("max", "2026-10-26")
    jour.get_by_label("Jour", exact=True).fill("2026-10-23")
    expect(jour.get_by_label("Jour", exact=True)).to_have_value("2026-10-24")
    assert (camera["id"], "2026-10-23") not in demandes

    # Le jour choisi suit l'Administrateur d'une Caméra à l'autre.
    jour.get_by_label("Jour", exact=True).fill("2026-10-25")
    expect(_plages(relecture)).to_have_count(1)
    enregistrement.get_by_role("combobox", name="Caméra").select_option(str(autre["id"]))
    autre_relecture = _relecture(enregistrement, autre["nom"])
    expect(autre_relecture.get_by_text(SANS_SEGMENT)).to_be_visible()
    assert demandes[-1] == (autre["id"], "2026-10-25")


@pytest.mark.parametrize("duree_h", [23, 25])
def test_la_timeline_d_un_jour_de_changement_d_heure_suit_sa_duree_reelle(enregistrement: Page, api, noms, duree_h):
    camera = _camera(api, noms, url_injoignable())
    debut_jour = datetime(2026, 10, 24, 22, tzinfo=UTC)
    fenetre = (debut_jour, debut_jour + timedelta(hours=duree_h))
    # Une plage d'une heure, la 22e heure du jour.
    plage = (debut_jour + timedelta(hours=21), debut_jour + timedelta(hours=22))
    _simuler_segments(enregistrement, camera["id"], fenetre, [plage])
    enregistrement.goto(f"/relecture/{camera['id']}")

    timeline = _relecture(enregistrement, camera["nom"]).get_by_role("button", name="Timeline d’enregistrement")

    expect(_plages(timeline)).to_have_count(1)
    boite, place = timeline.bounding_box(), _plages(timeline).bounding_box()
    assert boite
    assert place
    assert place["x"] - boite["x"] == pytest.approx(boite["width"] * 21 / duree_h, abs=2)
    assert place["width"] == pytest.approx(boite["width"] / duree_h, abs=2)


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

    timeline = relecture.get_by_role("button", name="Timeline d’enregistrement")
    plages = _plages(timeline)
    expect(plages).to_have_count(2)
    boite = timeline.bounding_box()
    premiere, seconde = plages.nth(0).bounding_box(), plages.nth(1).bounding_box()
    assert boite
    assert premiere
    assert seconde
    # 10 min sur 60 commencent après 10 min, 5 min colorées, puis un trou de 25 min avant la seconde plage.
    assert premiere["x"] - boite["x"] == pytest.approx(boite["width"] * 10 / 60, abs=2)
    assert premiere["width"] == pytest.approx(boite["width"] * 5 / 60, abs=2)
    assert seconde["x"] - (premiere["x"] + premiere["width"]) == pytest.approx(boite["width"] * 25 / 60, abs=2)
    expect(relecture.get_by_text(SANS_SEGMENT)).to_have_count(0)


def test_camera_sans_segment_affiche_un_message(enregistrement: Page, api, noms):
    camera = _camera(api, noms, url_injoignable())

    relecture = _selectionner(enregistrement, camera["nom"])

    expect(relecture.get_by_text(SANS_SEGMENT)).to_be_visible()
    expect(_plages(relecture)).to_have_count(0)
    expect(relecture.locator("video")).to_have_count(0)


def test_clic_sur_une_plage_part_de_la_seconde_visee(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_injoignable())
    maintenant = _maintenant()
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    ancien = (maintenant - timedelta(minutes=50), maintenant - timedelta(minutes=45))
    recent = (maintenant - timedelta(minutes=20), maintenant - timedelta(minutes=10))
    _simuler_segments(enregistrement, camera["id"], fenetre, [ancien, recent])
    relecture = _selectionner(enregistrement, camera["nom"])
    timeline = relecture.get_by_role("button", name="Timeline d’enregistrement")

    # Dans le Segment ancien, à 47 min d'ici : l'instant cliqué, pas le début du Segment.
    _cliquer_a(timeline, 13 / 60)
    expect(_plage_lue(relecture)).to_have_count(1)
    _attendre(enregistrement, lambda: len(relectures) >= 1)
    start = datetime.fromisoformat(_debut_demande(relectures[-1]))
    assert abs((start - (maintenant - timedelta(minutes=47))).total_seconds()) < PRECISION_CLIC_S
    parametres = parse_qs(urlparse(relectures[-1]).query)
    assert parametres["path"] == [camera["chemin_flux"]]
    # Fenêtre coupée à la fin de la Plage : 2 min, sous les 3 min de la fenêtre glissante.
    assert float(parametres["duration"][0]) == pytest.approx((ancien[1] - start).total_seconds(), abs=0.01)
    expect(relecture.get_by_label("Instant lu")).to_have_text(start.strftime("%H:%M:%S"))

    # Dans le trou, plus près du Segment récent (à 30 min d'ici : 10 min de son début, 15 min de la fin de l'ancien).
    _cliquer_a(timeline, 30 / 60)
    _attendre(enregistrement, lambda: len(relectures) >= 2)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == recent[0]


def test_au_clavier_la_timeline_passe_au_segment_suivant(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_injoignable())
    maintenant = _maintenant()
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    ancien = (maintenant - timedelta(minutes=50), maintenant - timedelta(minutes=45))
    recent = (maintenant - timedelta(minutes=20), maintenant - timedelta(minutes=10))
    _simuler_segments(enregistrement, camera["id"], fenetre, [ancien, recent])
    relecture = _selectionner(enregistrement, camera["nom"])
    timeline = relecture.get_by_role("button", name="Timeline d’enregistrement")

    # Sans Segment courant, Entrée part du premier ; puis Espace passe au suivant.
    timeline.press("Enter")
    _attendre(enregistrement, lambda: len(relectures) >= 1)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == ancien[0]
    timeline.press("Space")
    _attendre(enregistrement, lambda: len(relectures) >= 2)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == recent[0]


def test_la_timeline_se_rafraichit_et_l_enchainement_attend_le_segment_ferme_ensuite(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_injoignable())
    maintenant = _maintenant()
    fenetre = (maintenant - timedelta(hours=1), maintenant)
    ancien = (maintenant - timedelta(minutes=3), maintenant - timedelta(minutes=2))
    ferme_ensuite = (maintenant - timedelta(minutes=2), maintenant - timedelta(minutes=1))
    lectures = 0

    def segments(route: Route) -> None:
        nonlocal lectures
        lectures += 1
        plages = [ancien] if lectures == 1 else [ancien, ferme_ensuite]
        route.fulfill(json=_corps(fenetre, plages))

    enregistrement.route(f"**/api/cameras/{camera['id']}/segments*", segments)
    relecture = _selectionner(enregistrement, camera["nom"])
    _cliquer_a(relecture.get_by_role("button", name="Timeline d’enregistrement"), 57.5 / 60)
    _attendre(enregistrement, lambda: len(relectures) >= 1)

    # Fin du dernier Segment connu : le viewer attend le rafraîchissement qui apporte le Segment fermé depuis.
    relecture.locator("video").dispatch_event("ended")
    expect(_plages(relecture)).to_have_count(2, timeout=DELAI_RAFRAICHISSEMENT_MS)
    _attendre(enregistrement, lambda: len(relectures) >= 2)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) == ferme_ensuite[0]
    expect(_plage_lue(relecture)).to_have_count(1)


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

    _cliquer_a(relecture.get_by_role("button", name="Timeline d’enregistrement"), 30.5 / 60)

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
    """Jour réduit aux Segments réels : des Segments de 2 s tiennent moins d'un pixel sur une journée."""

    def resserrer(route: Route) -> None:
        reponse = route.fetch()
        corps = reponse.json()
        if corps["segments"]:
            corps["debut_jour"], corps["fin_jour"] = corps["segments"][0]["debut"], corps["segments"][-1]["fin"]
        route.fulfill(response=reponse, json=corps)

    page.route(f"**/api/cameras/{id_camera}/segments*", resserrer)


def _cliquer_au_milieu(timeline: Locator, plage: Locator) -> None:
    boite, place = timeline.bounding_box(), plage.bounding_box()
    assert boite
    assert place
    _cliquer_a(timeline, (place["x"] - boite["x"] + place["width"] / 2) / boite["width"])


def _milieu(segment: dict) -> datetime:
    debut, fin = datetime.fromisoformat(segment["debut"]), datetime.fromisoformat(segment["fin"])
    return debut + (fin - debut) / 2


def test_relire_une_plage_seek_play_pause_vitesses_et_enchainement(enregistrement: Page, api, noms, relectures):
    camera = _camera(api, noms, url_simulee(1))
    assert api.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    raccourcir_les_segments(camera["chemin_flux"], DELAI_PONT_S)
    segments = _segments_fermes(api, camera["id"], 3)
    _resserrer_la_fenetre(enregistrement, camera["id"])
    relecture = _selectionner(enregistrement, camera["nom"])
    video = relecture.locator("video")
    timeline = relecture.get_by_role("button", name="Timeline d’enregistrement")

    # Au milieu du premier Segment : la vidéo part de cette seconde, pas du début du Segment, et joue.
    _cliquer_au_milieu(timeline, _plages(relecture).first)
    expect(video).to_have_js_property("paused", False, timeout=DELAI_VIDEO_MS)
    _attendre(enregistrement, lambda: video.evaluate("v => v.currentTime") > 0.2, DELAI_VIDEO_MS / 1000)
    start = datetime.fromisoformat(_debut_demande(relectures[0]))
    assert abs((start - _milieu(segments[0])).total_seconds()) < 0.5
    expect(relecture.get_by_role("progressbar", name="Progression dans la Plage")).to_be_visible()
    expect(relecture.get_by_label("Instant lu")).to_have_text(re.compile(r"^\d{2}:\d{2}:\d{2}$"))

    # En lecture, un clic ailleurs repart de cette seconde, et la lecture continue.
    _cliquer_au_milieu(timeline, _plages(relecture).nth(2))
    _attendre(enregistrement, lambda: len(relectures) >= 2)
    assert abs((datetime.fromisoformat(_debut_demande(relectures[-1])) - _milieu(segments[2])).total_seconds()) < 0.5
    expect(video).to_have_js_property("paused", False, timeout=DELAI_VIDEO_MS)
    _attendre(enregistrement, lambda: video.evaluate("v => v.currentTime") > 0.2, DELAI_VIDEO_MS / 1000)

    relecture.get_by_role("button", name="Pause").click()
    expect(video).to_have_js_property("paused", True)
    relecture.get_by_role("button", name="Lecture").click()
    expect(video).to_have_js_property("paused", False)

    for vitesse in VITESSES:
        relecture.get_by_role("button", name=f"×{vitesse}", exact=True).click()
        expect(video).to_have_js_property("playbackRate", vitesse)
        expect(relecture.get_by_role("button", name=f"×{vitesse}", exact=True)).to_have_attribute("aria-pressed", "true")

    # À ×16, la fenêtre s'achève vite : le viewer reprend après elle, dès que la Timeline la prolonge, à la même vitesse.
    demandees = len(relectures)
    _attendre(enregistrement, lambda: len(relectures) > demandees, (DELAI_VIDEO_MS + DELAI_RAFRAICHISSEMENT_MS) / 1000)
    assert datetime.fromisoformat(_debut_demande(relectures[-1])) > datetime.fromisoformat(segments[2]["debut"])
    expect(video).to_have_js_property("playbackRate", 16)
