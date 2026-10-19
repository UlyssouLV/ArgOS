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
