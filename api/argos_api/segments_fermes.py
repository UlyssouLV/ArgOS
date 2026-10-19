"""Segments fermés d'une Caméra sur la fenêtre de Conservation, pour la Relecture (ADR 0013)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from argos_api.cameras import AGE_MAX_DERNIER_SEGMENT_S
from argos_api.pont import chemin_flux

# recordPath du pont (media/mediamtx.yml) : `%Y-%m-%d_%H-%M-%S-%f`, heure UTC du conteneur, suffixe `.mp4`.
FORMAT_NOM_SEGMENT = "%Y-%m-%d_%H-%M-%S-%f"
SUFFIXE_SEGMENT = ".mp4"


class SegmentFerme(BaseModel):
    debut: datetime
    fin: datetime


class SegmentsFermes(BaseModel):
    """Fenêtre de Conservation (`debut` → `fin` = maintenant) et Segments fermés qui la touchent, du plus ancien."""

    debut: datetime
    fin: datetime
    segments: list[SegmentFerme]


def lire(racine: Path, id_camera: int, enregistrement: bool, conservation_h: int, maintenant: datetime) -> SegmentsFermes:
    """Début lu dans le nom du fichier, fin = dernière écriture. Le dernier Segment est tenu pour encore ouvert
    tant que l'Enregistrement est ON et qu'il a été écrit il y a moins de `AGE_MAX_DERNIER_SEGMENT_S`."""
    debut_conservation = maintenant - timedelta(hours=conservation_h)
    segments = sorted(_segments(racine / chemin_flux(id_camera)), key=lambda s: s.debut)
    if segments and enregistrement and (maintenant - segments[-1].fin).total_seconds() < AGE_MAX_DERNIER_SEGMENT_S:
        segments.pop()
    return SegmentsFermes(
        debut=debut_conservation,
        fin=maintenant,
        segments=[s for s in segments if s.fin >= debut_conservation],
    )


def _segments(dossier: Path) -> list[SegmentFerme]:
    if not dossier.is_dir():
        return []
    lus: list[SegmentFerme] = []
    try:
        for chemin in dossier.iterdir():
            segment = _segment(chemin)
            if segment is not None:
                lus.append(segment)
    except OSError:
        return []
    return lus


def _segment(chemin: Path) -> SegmentFerme | None:
    if chemin.suffix != SUFFIXE_SEGMENT:
        return None
    try:
        debut = datetime.strptime(chemin.stem, FORMAT_NOM_SEGMENT).replace(tzinfo=UTC)
        if not chemin.is_file():
            return None
        fin = datetime.fromtimestamp(chemin.stat().st_mtime, UTC)
    except (ValueError, OSError):
        return None
    return SegmentFerme(debut=debut, fin=max(debut, fin))
