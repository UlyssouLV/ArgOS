"""Segments d'une Caméra sur disque : nom donné par le pont, fin à la dernière écriture. Sans dépendance hors stdlib,
comme `relecture`, qui s'en sert."""

from datetime import UTC, datetime
from pathlib import Path

# recordPath du pont (media/mediamtx.yml) : `%Y-%m-%d_%H-%M-%S-%f`, heure UTC du conteneur, suffixe `.mp4`.
FORMAT_NOM_SEGMENT = "%Y-%m-%d_%H-%M-%S-%f"
SUFFIXE_SEGMENT = ".mp4"


def segments_du_dossier(dossier: Path) -> list[tuple[datetime, Path]]:
    """Segments du dossier repérés par le début lu dans leur nom, sans toucher aux fichiers ; aucun s'il est illisible."""
    try:
        chemins = list(dossier.iterdir())
    except OSError:
        return []
    lus = []
    for chemin in chemins:
        if chemin.suffix != SUFFIXE_SEGMENT:
            continue
        try:
            lus.append((datetime.strptime(chemin.stem, FORMAT_NOM_SEGMENT).replace(tzinfo=UTC), chemin))
        except ValueError:
            continue
    return lus


def derniere_ecriture(chemin: Path) -> datetime | None:
    """Fin d'un Segment : dernière écriture de son fichier ; `None` s'il n'est pas lisible."""
    try:
        if not chemin.is_file():
            return None
        return datetime.fromtimestamp(chemin.stat().st_mtime, UTC)
    except OSError:
        return None
