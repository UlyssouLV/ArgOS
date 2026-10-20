"""Relecture d'un Segment fermé par le serveur playback du pont, relayé par nginx derrière la session (ADR 0013).

Le pont coupe ses Segments à 1 min : le test raccourcit ceux du chemin de sa Caméra par l'API de contrôle, pour
qu'un Segment se ferme en quelques secondes.
"""

import time
from datetime import datetime

import httpx
import pytest

from stack_compose import client_du_site, raccourcir_les_segments
from test_cameras import connecte, creer_camera  # noqa: F401 (fixtures)
from test_enregistrement import DELAI_PONT_S
from test_etat_cameras import url_simulee
from test_relecture_video_seule import gestionnaires

CHEMIN_RELECTURE = "/flux/relecture/get"
DELAI_SEGMENT_FERME_S = 60
# Échantillon vidéo du `moov` : le codec de la Caméra simulée, remballé sans réencodage (ADR 0004 pour hvc1).
# La 4 annonce aussi une piste audio PCM, que la relecture retire (bug #141).
ENTREES_CODEC = {1: b"avc1", 4: b"hvc1"}


def url_relecture(chemin: str, debut: str, duree_s: float) -> httpx.URL:
    return httpx.URL(
        CHEMIN_RELECTURE, params={"path": chemin, "start": debut, "duration": f"{duree_s:.3f}", "format": "mp4"}
    )


def _attendre_un_segment_ferme(client: httpx.Client, id_camera: int) -> dict:
    """Premier Segment fermé d'au moins 1 s : avec une piste audio, le pont ouvre d'abord un Segment de quelques
    dixièmes de seconde, audio seul, avant la première image clé vidéo."""
    echeance = time.monotonic() + DELAI_SEGMENT_FERME_S
    while True:
        segments = client.get(f"/api/cameras/{id_camera}/segments").json()["segments"]
        avec_video = [segment for segment in segments if _duree_s(segment) >= 1]
        if avec_video:
            return avec_video[0]
        if time.monotonic() > echeance:
            pytest.fail(f"aucun Segment fermé pour la Caméra {id_camera} après {DELAI_SEGMENT_FERME_S} s")
        time.sleep(1)


@pytest.fixture
def segment_ferme(connecte, creer_camera):
    """Caméra simulée `numero` qui enregistre, et son premier Segment fermé : (chemin du pont, Segment)."""

    def _segment(numero: int) -> tuple[str, dict]:
        camera = creer_camera(url_rtsp=url_simulee(numero)).json()
        assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
        raccourcir_les_segments(camera["chemin_flux"], DELAI_PONT_S)
        return camera["chemin_flux"], _attendre_un_segment_ferme(connecte, camera["id"])

    return _segment


def _duree_s(segment: dict) -> float:
    return (datetime.fromisoformat(segment["fin"]) - datetime.fromisoformat(segment["debut"])).total_seconds()


@pytest.mark.parametrize("numero", sorted(ENTREES_CODEC))
def test_un_segment_ferme_se_relit_en_mp4_video_seule_sans_reencodage(connecte, segment_ferme, numero):
    chemin, segment = segment_ferme(numero)

    reponse = connecte.get(url_relecture(chemin, segment["debut"], max(_duree_s(segment), 1)))

    assert reponse.status_code == 200, reponse.text
    assert reponse.headers["content-type"] == "video/mp4"
    assert reponse.content[4:8] == b"ftyp"
    moov = reponse.content[: reponse.content.find(b"mdat")]
    assert ENTREES_CODEC[numero] in moov
    assert gestionnaires(reponse.content) == [b"vide"]


def test_un_segment_ferme_relu_par_une_session_est_refuse_sans_elle(connecte, segment_ferme):
    chemin, segment = segment_ferme(1)
    url = url_relecture(chemin, segment["debut"], 1)
    assert connecte.get(url).status_code == 200

    with client_du_site() as sans_session:
        assert sans_session.get(url).status_code == 401


def test_un_segment_ferme_se_relit_par_plages_d_octets_comme_safari(connecte, segment_ferme):
    """Safari ouvre la `<video>` par `Range: bytes=0-1` et refuse tout sauf un `206` (#143)."""
    chemin, segment = segment_ferme(4)
    url = url_relecture(chemin, segment["debut"], max(_duree_s(segment), 1))

    entier = connecte.get(url)
    assert entier.status_code == 200, entier.text
    assert entier.headers["accept-ranges"] == "bytes"
    assert int(entier.headers["content-length"]) == len(entier.content)
    assert gestionnaires(entier.content) == [b"vide"]
    taille = len(entier.content)

    debut = connecte.get(url, headers={"Range": "bytes=0-1"})
    assert debut.status_code == 206
    assert debut.headers["content-range"] == f"bytes 0-1/{taille}"
    assert debut.content == entier.content[:2]

    milieu = connecte.get(url, headers={"Range": f"bytes={taille // 2}-{taille // 2 + 99}"})
    assert milieu.status_code == 206
    assert milieu.content == entier.content[taille // 2 : taille // 2 + 100]

    hors = connecte.get(url, headers={"Range": f"bytes={taille}-"})
    assert hors.status_code == 416
    assert hors.headers["content-range"] == f"bytes */{taille}"
