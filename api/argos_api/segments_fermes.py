"""Segments fermés d'une Caméra sur un jour du Site, pour la Relecture (ADR 0013, ADR 0017)."""

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from argos_api.cameras import AGE_MAX_DERNIER_SEGMENT_S
from argos_api.pont import chemin_flux
from argos_api.relecture import segments_du_dossier


class SegmentFerme(BaseModel):
    debut: datetime
    fin: datetime


class SegmentsFermes(BaseModel):
    """Fenêtre de Conservation (`debut` → `fin` = maintenant), ses jours au fuseau du Site (`premier_jour` →
    `dernier_jour`), le `jour` relu (`debut_jour` → `fin_jour`, 23 à 25 h) et ses Segments fermés, du plus ancien."""

    debut: datetime
    fin: datetime
    fuseau: str
    premier_jour: date
    dernier_jour: date
    jour: date
    debut_jour: datetime
    fin_jour: datetime
    segments: list[SegmentFerme]


def lire(
    racine: Path,
    id_camera: int,
    enregistrement: bool,
    conservation_h: int,
    maintenant: datetime,
    fuseau: str,
    jour: date | None = None,
) -> SegmentsFermes:
    """Segments fermés qui touchent `jour` (le jour courant par défaut) et la Conservation. Début lu dans le nom du
    fichier, fin = dernière écriture. Le dernier Segment est tenu pour encore ouvert tant que l'Enregistrement est ON
    et qu'il a été écrit il y a moins de `AGE_MAX_DERNIER_SEGMENT_S`."""
    zone = ZoneInfo(fuseau)
    debut_conservation = maintenant - timedelta(hours=conservation_h)
    jour = jour or maintenant.astimezone(zone).date()
    debut_jour = _minuit(jour, zone)
    fin_jour = _minuit(jour + timedelta(days=1), zone)

    fichiers = sorted(segments_du_dossier(racine / chemin_flux(id_camera)))
    if fichiers and enregistrement:
        dernier = _segment(*fichiers[-1])
        if dernier is None or (maintenant - dernier.fin).total_seconds() < AGE_MAX_DERNIER_SEGMENT_S:
            fichiers.pop()
    # Seule la date du nom borne la recherche : sur 30 jours, on ne lit la fin (stat) que des Segments du jour, plus
    # le dernier commencé avant, qui peut franchir minuit (les Segments d'une Caméra se suivent sans se chevaucher).
    avant = [f for f in fichiers if f[0] < debut_jour][-1:]
    du_jour = [f for f in fichiers if debut_jour <= f[0] < fin_jour]
    segments = [s for s in (_segment(*f) for f in avant + du_jour) if s is not None]
    return SegmentsFermes(
        debut=debut_conservation,
        fin=maintenant,
        fuseau=fuseau,
        premier_jour=debut_conservation.astimezone(zone).date(),
        dernier_jour=maintenant.astimezone(zone).date(),
        jour=jour,
        debut_jour=debut_jour,
        fin_jour=fin_jour,
        segments=[s for s in segments if s.fin > debut_jour and s.fin >= debut_conservation],
    )


def debut_plus_ancien(racine: Path, id_camera: int) -> datetime | None:
    """Début du plus ancien Segment de la Caméra, lu dans son nom ; `None` : aucun."""
    return min((debut for debut, _ in segments_du_dossier(racine / chemin_flux(id_camera))), default=None)


def _minuit(jour: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(jour, time(), zone).astimezone(UTC)


def _segment(debut: datetime, chemin: Path) -> SegmentFerme | None:
    try:
        if not chemin.is_file():
            return None
        fin = datetime.fromtimestamp(chemin.stat().st_mtime, UTC)
    except OSError:
        return None
    return SegmentFerme(debut=debut, fin=max(debut, fin))
