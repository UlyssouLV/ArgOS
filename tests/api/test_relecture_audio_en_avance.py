"""Caméra simulée 6, l'audio horodaté en avance sur la vidéo comme Cam 01 (#173) : ce que le pont en enregistre,
et la relecture de ses Segments (ADR 0018, « Un Segment par fenêtre »).

Au début de chaque lecture, l'audio de la 6 prend AVANCE_AUDIO_S secondes d'avance sur sa vidéo : le pont ouvre
alors chaque Segment à l'heure de l'audio et jette la vidéo arrivée « trop tard », image clé comprise. Les Segments
sont raccourcis à DUREE_SEGMENTS_S (plus que l'avance, comme la minute du pont face aux ~14 s de Cam 01).
"""

import base64
import subprocess
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from argos_api.segments import FORMAT_NOM_SEGMENT, SUFFIXE_SEGMENT
from stack_compose import compose, raccourcir_les_segments
from test_cameras import connecte, creer_camera  # noqa: F401 (fixtures)
from test_enregistrement import DELAI_PONT_S
from test_etat_cameras import url_simulee
from test_relecture import url_relecture
from test_relecture_video_seule import gestionnaires

NUMERO = 6
# AVANCE_AUDIO_S de camera-simulee-6 (compose.simulation.yaml).
AVANCE_AUDIO_S = 14
DUREE_SEGMENTS_S = 20
# Le temps que l'audio prenne son avance : le pont se recale plusieurs fois (« detected drift ») avant de s'y tenir.
DELAI_AVANCE_S = AVANCE_AUDIO_S + 10
# Deux Segments fermés après l'avance prise, chacun d'environ DUREE_SEGMENTS_S + AVANCE_AUDIO_S, plus celui à cheval
# sur DELAI_AVANCE_S et un de marge : à la première ouverture du chemin, deux suffisaient à peine sur un runner chargé.
DELAI_SEGMENTS_S = DELAI_PONT_S + DELAI_AVANCE_S + 4 * (DUREE_SEGMENTS_S + AVANCE_AUDIO_S)
IMAGE_FFPROBE = "linuxserver/ffmpeg:version-7.1-cli"
# Piste 1 des Segments : la vidéo, premier média annoncé par la Caméra simulée.
VIDEO_JETEE = "[recorder] sample of track 1 received too late, discarding"


def _instant(segment: dict, cle: str) -> datetime:
    return datetime.fromisoformat(segment[cle])


def _paquets_video(mp4: bytes) -> list[tuple[float, float, str]]:
    """(pts, durée, drapeaux) des paquets de la première piste vidéo, lus par ffprobe sur l'entrée standard."""
    resultat = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "--entrypoint", "ffprobe",
            IMAGE_FFPROBE,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "packet=pts_time,duration_time,flags",
            "-of", "csv=p=0",
            "pipe:0",
        ],
        input=mp4,
        capture_output=True,
        check=True,
    )
    paquets = []
    for ligne in resultat.stdout.decode().splitlines():
        pts, duree, drapeaux = ligne.split(",")[:3]
        paquets.append((float(pts), float(duree), drapeaux))
    return paquets


def _duree_video_s(paquets: list[tuple[float, float, str]]) -> float:
    return paquets[-1][0] + paquets[-1][1] - paquets[0][0]


def _fichier_du_segment(id_camera: int, segment: dict) -> bytes:
    """Le fichier du Segment, lu sur le volume par `api` (en base64 : la sortie de `compose` est du texte)."""
    nom = _instant(segment, "debut").astimezone(UTC).strftime(FORMAT_NOM_SEGMENT) + SUFFIXE_SEGMENT
    return base64.b64decode(compose("exec", "-T", "api", "base64", f"/enregistrements/camera-{id_camera}/{nom}").stdout)


def _segments_apres_l_avance(client: httpx.Client, id_camera: int, depuis: datetime, nombre: int) -> list[dict]:
    """`nombre` Segments fermés et contigus, ouverts une fois l'avance de l'audio prise (après `depuis`)."""
    echeance = time.monotonic() + DELAI_SEGMENTS_S
    while True:
        segments = client.get(f"/api/cameras/{id_camera}/segments").json()["segments"]
        apres = [s for s in segments if _instant(s, "debut") >= depuis + timedelta(seconds=DELAI_AVANCE_S)]
        if len(apres) >= nombre:
            return apres[:nombre]
        if time.monotonic() > echeance:
            pytest.fail(f"{len(apres)} Segment(s) fermé(s) après l'avance de l'audio en {DELAI_SEGMENTS_S} s")
        time.sleep(2)


@pytest.fixture
def enregistree(connecte, creer_camera):
    """Caméra simulée 6 qui enregistre, Segments raccourcis : (Caméra, deux Segments fermés après l'avance)."""
    depuis = datetime.now().astimezone()
    camera = creer_camera(url_rtsp=url_simulee(NUMERO)).json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    raccourcir_les_segments(camera["chemin_flux"], DELAI_PONT_S, f"{DUREE_SEGMENTS_S}s")
    return camera, _segments_apres_l_avance(connecte, camera["id"], depuis, 2)


def test_le_pont_jette_la_video_du_debut_de_chaque_segment(enregistree):
    """Comme chez Cam 01 : vidéo plus courte que l'heure réelle, qui commence par des images P."""
    camera, segments = enregistree

    for segment in segments:
        paquets = _paquets_video(_fichier_du_segment(camera["id"], segment))
        duree_reelle = (_instant(segment, "fin") - _instant(segment, "debut")).total_seconds()
        assert duree_reelle - _duree_video_s(paquets) > AVANCE_AUDIO_S / 2, (duree_reelle, _duree_video_s(paquets))
        assert "K" not in paquets[0][2], paquets[:3]
    journal = compose("logs", "--no-log-prefix", "--since", segments[0]["debut"], "mediamtx").stdout
    assert f"[path {camera['chemin_flux']}] {VIDEO_JETEE}" in journal


def test_la_fin_de_chaque_segment_se_relit_en_video(connecte, enregistree):
    """La vidéo d'un Segment finit à sa fin réelle : ses dernières secondes se relisent (fenêtre recalée, #172)."""
    camera, segments = enregistree

    for segment in segments:
        debut = _instant(segment, "fin") - timedelta(seconds=5)
        reponse = connecte.get(url_relecture(camera["chemin_flux"], debut.isoformat(), 5))

        assert reponse.status_code == 200, reponse.text
        assert gestionnaires(reponse.content) == [b"vide"]
        assert _duree_video_s(_paquets_video(reponse.content)) >= 3
