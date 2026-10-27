"""Fenêtre recalée sur la vidéo d'un Segment plus court en vidéo qu'en heure réelle (#172, tests unitaires).

Cam 01 horodate son audio en avance sur sa vidéo : le pont ouvre chaque Segment à l'heure de l'audio et jette la
vidéo arrivée « trop tard ». La vidéo d'un Segment finit à sa fin réelle, mais commence plus tard que son nom :
l'API décale la fenêtre demandée d'autant, pour que l'image lue soit celle de l'instant visé.
"""

import os
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from argos_api import relecture

VIDEO, AUDIO = 1, 2
ECHELLE_VIDEO, ECHELLE_AUDIO = 90_000, 8_000


def boite(type_: bytes, *contenus: bytes) -> bytes:
    contenu = b"".join(contenus)
    return struct.pack(">I4s", 8 + len(contenu), type_) + contenu


def boite_complete(type_: bytes, contenu: bytes, version: int = 0, drapeaux: int = 0) -> bytes:
    return boite(type_, struct.pack(">I", version << 24 | drapeaux) + contenu)


def piste(id_piste: int, gestionnaire: bytes, echelle: int) -> bytes:
    tkhd = boite_complete(b"tkhd", struct.pack(">III", 0, 0, id_piste) + b"\0" * 68)
    mdhd = boite_complete(b"mdhd", struct.pack(">III", 0, 0, echelle) + b"\0" * 8)
    hdlr = boite_complete(b"hdlr", b"\0\0\0\0" + gestionnaire + b"\0" * 13)
    return boite(b"trak", tkhd, boite(b"mdia", mdhd, hdlr, boite(b"minf", boite(b"stbl"))))


def fragment(id_piste: int, base: int, durees: list[int]) -> bytes:
    """`moof` d'une piste : `tfdt` (version 1) puis une durée par échantillon dans `trun`, et son `mdat`."""
    tfhd = boite_complete(b"tfhd", struct.pack(">I", id_piste))
    tfdt = boite_complete(b"tfdt", struct.pack(">Q", base), version=1)
    trun = boite_complete(b"trun", struct.pack(">I", len(durees)) + b"".join(struct.pack(">I", d) for d in durees), drapeaux=0x100)
    return boite(b"moof", boite(b"mfhd", b"\0" * 8), boite(b"traf", tfhd, tfdt, trun)) + boite(b"mdat", b"\0" * 32)


def segment_fmp4(video: tuple[float, float] | None, audio: tuple[float, float]) -> bytes:
    """Segment du pont : piste vidéo de `video[0]` à `video[1]` s (images de 50 ms), audio de même, depuis son début."""
    pistes = [piste(AUDIO, b"soun", ECHELLE_AUDIO)]
    fragments = [fragment(AUDIO, int(audio[0] * ECHELLE_AUDIO), [int((audio[1] - audio[0]) * ECHELLE_AUDIO)])]
    if video is not None:
        pistes.insert(0, piste(VIDEO, b"vide", ECHELLE_VIDEO))
        debut, fin = video
        images = round((fin - debut) / 0.05)
        moitie = images // 2
        fragments += [
            fragment(VIDEO, int(debut * ECHELLE_VIDEO), [4500] * moitie),
            fragment(VIDEO, int((debut + moitie * 0.05) * ECHELLE_VIDEO), [4500] * (images - moitie)),
        ]
    ftyp = boite(b"ftyp", b"iso5\0\0\x02\0iso5iso6mp41")
    return ftyp + boite(b"moov", boite_complete(b"mvhd", b"\0" * 96), *pistes) + b"".join(fragments)


def test_la_fin_de_la_video_d_un_segment_compte_depuis_son_debut(tmp_path: Path):
    chemin = tmp_path / "segment.mp4"
    chemin.write_bytes(segment_fmp4(video=(0.017, 61.717), audio=(0, 76.08)))

    assert relecture.fin_de_la_video(chemin) == pytest.approx(61.717, abs=0.001)


def test_un_segment_sans_video_ou_illisible_n_a_pas_de_fin_de_video(tmp_path: Path):
    sans_video = tmp_path / "audio.mp4"
    sans_video.write_bytes(segment_fmp4(video=None, audio=(0, 2)))
    tronque = tmp_path / "tronque.mp4"
    tronque.write_bytes(segment_fmp4(video=(0, 2), audio=(0, 2))[:40])

    assert relecture.fin_de_la_video(sans_video) is None
    assert relecture.fin_de_la_video(tronque) is None
    assert relecture.fin_de_la_video(tmp_path / "absent.mp4") is None


DEBUT = datetime(2026, 10, 27, 7, 19, 43, 697104, tzinfo=UTC)
SUIVANT = DEBUT + timedelta(seconds=76.08)


@pytest.fixture
def cam01(tmp_path: Path) -> Path:
    """Dossier `camera-2` : deux Segments comme ceux de Cam 01, vidéo 61,7 s pour 76,08 s d'heure réelle."""
    dossier = tmp_path / "camera-2"
    dossier.mkdir()
    for debut in (DEBUT, SUIVANT):
        chemin = dossier / f"{debut.strftime(relecture.FORMAT_NOM_SEGMENT)}.mp4"
        chemin.write_bytes(segment_fmp4(video=(0.017, 61.717), audio=(0, 76.08)))
        fin = debut + timedelta(seconds=76.08)
        os.utime(chemin, (fin.timestamp(), fin.timestamp()))
    return tmp_path


def _recaler(racine: Path, debut: datetime, duree_s: float, chemin: str = "camera-2") -> tuple[datetime, float]:
    return relecture.recaler(racine, chemin, debut, duree_s)


def test_la_fenetre_se_decale_de_la_video_jetee_au_debut_du_segment(cam01: Path):
    # 14,363 s d'heure réelle sans vidéo au début du Segment : l'image de 07:20:13 est 14,363 s plus tôt dans sa vidéo.
    vise = datetime(2026, 10, 27, 7, 20, 13, tzinfo=UTC)
    duree = (SUIVANT - vise).total_seconds()

    debut, duree_recalee = _recaler(cam01, vise, duree)

    assert (vise - debut).total_seconds() == pytest.approx(76.08 - 61.717, abs=0.001)
    # La fin reste celle du Segment : l'audio, en avance, y arrive avec la vidéo.
    assert debut + timedelta(seconds=duree_recalee) == SUIVANT


def test_une_fenetre_dans_la_video_jetee_part_du_debut_du_segment(cam01: Path):
    # Rien d'enregistré à cet instant : la fenêtre part de la première image du Segment, et finit avec lui.
    vise = DEBUT + timedelta(seconds=5)
    duree = (SUIVANT - vise).total_seconds()

    debut, duree_recalee = _recaler(cam01, vise, duree)

    assert debut == DEBUT
    assert duree_recalee == pytest.approx(76.08, abs=0.001)


def test_le_debut_du_segment_suivant_se_decale_aussi(cam01: Path):
    debut, _ = _recaler(cam01, SUIVANT, 76.08)

    assert debut == SUIVANT


@pytest.mark.parametrize("video", [(0.017, 76.08), (0, 76.5)])
def test_un_segment_dont_la_video_couvre_l_heure_reelle_ne_change_pas_la_fenetre(cam01: Path, video):
    chemin = min((cam01 / "camera-2").iterdir())
    mtime = chemin.stat().st_mtime
    chemin.write_bytes(segment_fmp4(video=video, audio=(0, 76.08)))
    os.utime(chemin, (mtime, mtime))
    vise = DEBUT + timedelta(seconds=30)

    assert _recaler(cam01, vise, 46.08) == (vise, 46.08)


@pytest.mark.parametrize(
    ("chemin", "vise"),
    [
        ("camera-2", DEBUT - timedelta(minutes=5)),
        ("camera-3", DEBUT + timedelta(seconds=30)),
        ("../camera-2", DEBUT + timedelta(seconds=30)),
        ("camera-2/..", DEBUT + timedelta(seconds=30)),
    ],
)
def test_hors_d_un_segment_connu_la_fenetre_passe_telle_quelle(cam01: Path, chemin, vise):
    assert _recaler(cam01, vise, 10, chemin) == (vise, 10)


def test_la_requete_du_pont_porte_la_fenetre_recalee(cam01: Path):
    requete = "path=camera-2&start=2026-10-27T07%3A20%3A13Z&duration=46.777&format=mp4"

    recalee = parse_qs(relecture.recaler_la_requete(cam01, requete))

    assert recalee["path"] == ["camera-2"]
    assert recalee["format"] == ["mp4"]
    assert recalee["start"] == ["2026-10-27T07:19:58.637000Z"]
    assert float(recalee["duration"][0]) == pytest.approx(46.777 + 14.363, abs=0.001)


def test_le_debut_d_un_segment_reste_a_la_microseconde(cam01: Path):
    requete = "path=camera-2&start=2026-10-27T07%3A19%3A48.697104Z&duration=71.08&format=mp4"

    assert parse_qs(relecture.recaler_la_requete(cam01, requete))["start"] == ["2026-10-27T07:19:43.697104Z"]


@pytest.mark.parametrize(
    "requete",
    [
        "path=camera-2&start=2026-10-27T07%3A10%3A00Z&duration=10&format=mp4",
        "path=camera-2&start=demain&duration=10",
        "path=camera-2&start=2026-10-27T07%3A20%3A13&duration=10",
        "path=camera-2&duration=10",
    ],
)
def test_une_requete_hors_segment_ou_illisible_passe_telle_quelle(cam01: Path, requete):
    assert relecture.recaler_la_requete(cam01, requete) == requete
