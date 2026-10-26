"""Relecture : Segments fermés d'une Caméra sur la fenêtre de Conservation (ADR 0013)."""

from datetime import UTC, datetime, timedelta

import pytest

from stack_compose import client_du_site, compose
from test_cameras import connecte, creer_camera  # noqa: F401

CONSERVATION_DEFAUT = 1


@pytest.fixture(autouse=True)
def conservation_remise(administrateur):
    def remettre() -> None:
        with client_du_site() as c:
            assert c.post(
                "/api/session",
                json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
            ).status_code == 204
            assert c.patch("/api/reglages-site", json={"conservation_h": CONSERVATION_DEFAUT}).status_code == 200

    remettre()
    yield
    remettre()


def _nom_pont(debut: datetime) -> str:
    """Nom MediaMTX `%Y-%m-%d_%H-%M-%S-%f.mp4` (heure UTC du conteneur pont)."""
    return debut.strftime("%Y-%m-%d_%H-%M-%S-%f") + ".mp4"


def _ecrire_segments(id_camera: int, segments: list[tuple[str, int]]) -> None:
    """Écrit des fichiers `(nom, âge de la dernière écriture en s)` sous `camera-<id>/`."""
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "import os, time\n"
        "from pathlib import Path\n"
        f"p = Path('/enregistrements/camera-{id_camera}'); p.mkdir(parents=True, exist_ok=True)\n"
        f"for nom, age in {segments!r}:\n"
        "    f = p / nom; f.write_bytes(b'x' * 1000)\n"
        "    t = time.time() - age; os.utime(f, (t, t))\n",
    )


def _instant(texte: str) -> datetime:
    return datetime.fromisoformat(texte)


def test_segments_sans_session_401(client):
    assert client.get("/api/cameras/1/segments").status_code == 401


def test_camera_inconnue_404(connecte):
    assert connecte.get("/api/cameras/999999/segments").status_code == 404


def test_camera_sans_segment_liste_vide(connecte, creer_camera):
    camera = creer_camera().json()

    reponse = connecte.get(f"/api/cameras/{camera['id']}/segments")

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["segments"] == []
    assert _instant(corps["fin"]) - _instant(corps["debut"]) == timedelta(hours=CONSERVATION_DEFAUT)


def test_segments_fermes_dans_l_ordre_avec_debut_et_fin(connecte, creer_camera):
    camera = creer_camera().json()
    maintenant = datetime.now(UTC)
    ancien = maintenant - timedelta(minutes=10)
    recent = maintenant - timedelta(minutes=5)
    # Fin = dernière écriture, une minute après le début.
    _ecrire_segments(camera["id"], [(_nom_pont(recent), 4 * 60), (_nom_pont(ancien), 9 * 60)])

    segments = connecte.get(f"/api/cameras/{camera['id']}/segments").json()["segments"]

    assert [_instant(s["debut"]) for s in segments] == [ancien, recent]
    for segment in segments:
        assert _instant(segment["fin"]) - _instant(segment["debut"]) == pytest.approx(
            timedelta(minutes=1), abs=timedelta(seconds=10)
        )


def test_segment_en_cours_d_ecriture_exclu(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    maintenant = datetime.now(UTC)
    ferme = maintenant - timedelta(minutes=2)
    ouvert = maintenant - timedelta(minutes=1)
    _ecrire_segments(camera["id"], [(_nom_pont(ferme), 60), (_nom_pont(ouvert), 1)])

    segments = connecte.get(f"/api/cameras/{camera['id']}/segments").json()["segments"]

    assert [_instant(s["debut"]) for s in segments] == [ferme]


def test_dernier_segment_ferme_si_enregistrement_a_l_arret(connecte, creer_camera):
    camera = creer_camera().json()
    dernier = datetime.now(UTC) - timedelta(minutes=1)
    _ecrire_segments(camera["id"], [(_nom_pont(dernier), 1)])

    segments = connecte.get(f"/api/cameras/{camera['id']}/segments").json()["segments"]

    assert [_instant(s["debut"]) for s in segments] == [dernier]


def test_segments_hors_conservation_et_fichiers_etrangers_ignores(connecte, creer_camera):
    camera = creer_camera().json()
    maintenant = datetime.now(UTC)
    garde = maintenant - timedelta(minutes=30)
    perime = maintenant - timedelta(hours=CONSERVATION_DEFAUT, minutes=5)
    _ecrire_segments(
        camera["id"],
        [
            (_nom_pont(garde), 29 * 60),
            (_nom_pont(perime), (CONSERVATION_DEFAUT * 60 + 4) * 60),
            ("notes.txt", 10 * 60),
            ("pas-une-date.mp4", 10 * 60),
        ],
    )

    segments = connecte.get(f"/api/cameras/{camera['id']}/segments").json()["segments"]

    assert [_instant(s["debut"]) for s in segments] == [garde]


# --- Relecture à la journée (ADR 0017) : `?jour=AAAA-MM-JJ`, jour civil au fuseau de l'Heure du Site. ---

# Assez pour garder les jours de changement d'heure de 2025 : posée en base, la borne de l'API ne s'applique pas.
CONSERVATION_LONGUE_H = 24 * 365 * 5
FUSEAU_DU_TEST = "Europe/Paris"


@pytest.fixture
def journees(connecte):
    """Site à Europe/Paris et Conservation longue, posés en base ; fuseau d'origine remis après le test."""
    from test_heure_du_site import psql

    avant = psql("SELECT coalesce(fuseau, '') FROM reglages_site WHERE id = 1")
    psql(f"UPDATE reglages_site SET fuseau = '{FUSEAU_DU_TEST}', conservation_h = {CONSERVATION_LONGUE_H} WHERE id = 1")
    yield
    psql(f"UPDATE reglages_site SET fuseau = {repr(avant) if avant else 'NULL'} WHERE id = 1")


def _ecrire_segments_d_une_minute(id_camera: int, debuts: list[datetime]) -> None:
    """Segments d'une minute (dernière écriture = début + 60 s), même anciens."""
    maintenant = datetime.now(UTC)
    _ecrire_segments(id_camera, [(_nom_pont(d), int((maintenant - d).total_seconds()) - 60) for d in debuts])


def _jour(connecte, id_camera: int, jour: str) -> dict:
    reponse = connecte.get(f"/api/cameras/{id_camera}/segments", params={"jour": jour})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


@pytest.mark.parametrize(
    ("jour", "debut_jour", "duree_h"),
    [
        # Jour ordinaire, jour de 23 h (passage à l'heure d'été), jour de 25 h (retour à l'heure d'hiver).
        ("2025-06-15", datetime(2025, 6, 14, 22, tzinfo=UTC), 24),
        ("2025-03-30", datetime(2025, 3, 29, 23, tzinfo=UTC), 23),
        ("2025-10-26", datetime(2025, 10, 25, 22, tzinfo=UTC), 25),
    ],
)
def test_jour_ne_rend_que_ses_segments_au_fuseau_du_site(connecte, creer_camera, journees, jour, debut_jour, duree_h):
    camera = creer_camera().json()
    fin_jour = debut_jour + timedelta(hours=duree_h)
    dedans = [debut_jour, debut_jour + timedelta(hours=12), fin_jour - timedelta(minutes=1)]
    # À cheval sur minuit en entrant : il touche le jour. Juste avant / juste à minuit le lendemain : non.
    a_cheval = debut_jour - timedelta(seconds=30)
    dehors = [debut_jour - timedelta(minutes=5), fin_jour, fin_jour + timedelta(hours=2)]
    _ecrire_segments_d_une_minute(camera["id"], [*dedans, a_cheval, *dehors])

    corps = _jour(connecte, camera["id"], jour)

    assert [_instant(s["debut"]) for s in corps["segments"]] == [a_cheval, *dedans]
    assert (corps["jour"], corps["fuseau"]) == (jour, FUSEAU_DU_TEST)
    assert _instant(corps["debut_jour"]) == debut_jour
    assert _instant(corps["fin_jour"]) - _instant(corps["debut_jour"]) == timedelta(hours=duree_h)


def test_sans_jour_le_jour_courant_au_fuseau_du_site(connecte, creer_camera, journees):
    from zoneinfo import ZoneInfo

    camera = creer_camera().json()
    hier = datetime.now(UTC) - timedelta(days=1, minutes=5)
    _ecrire_segments_d_une_minute(camera["id"], [hier])

    corps = connecte.get(f"/api/cameras/{camera['id']}/segments").json()

    assert corps["jour"] == datetime.now(ZoneInfo(FUSEAU_DU_TEST)).date().isoformat()
    assert corps["segments"] == []
    assert _instant(corps["debut_jour"]) <= datetime.now(UTC) < _instant(corps["fin_jour"])


def test_jours_de_la_conservation_au_fuseau_du_site(connecte, creer_camera, administrateur):
    """Conservation 1 h : premier et dernier jour sélectionnables, au fuseau du Site ; un jour avant est vide."""
    from zoneinfo import ZoneInfo

    camera = creer_camera().json()
    maintenant = datetime.now(UTC)
    corps = connecte.get(f"/api/cameras/{camera['id']}/segments").json()
    fuseau = ZoneInfo(corps["fuseau"])

    assert corps["premier_jour"] == (maintenant - timedelta(hours=CONSERVATION_DEFAUT)).astimezone(fuseau).date().isoformat()
    assert corps["dernier_jour"] == maintenant.astimezone(fuseau).date().isoformat()
    _ecrire_segments_d_une_minute(camera["id"], [maintenant - timedelta(days=2)])
    avant = (maintenant - timedelta(days=2)).astimezone(fuseau).date().isoformat()
    assert _jour(connecte, camera["id"], avant)["segments"] == []


@pytest.mark.parametrize("jour", ["2025-13-01", "hier", "2025-6-1"])
def test_jour_mal_forme_422(connecte, creer_camera, jour):
    camera = creer_camera().json()

    assert connecte.get(f"/api/cameras/{camera['id']}/segments", params={"jour": jour}).status_code == 422
