"""Débits d'écriture des Segments et estimation de tenue (ADR 0012)."""

import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from argos_api import reglages_site, segments_fermes
from argos_api.cameras import CameraLue, EtatEnregistrement
from argos_api.modeles import Camera
from argos_api.pont import chemin_flux

# Fenêtre des segments récents pour la mesure (ordre de quelques minutes MediaMTX).
FENETRE_MESURE_S = 300

SourceDebit = Literal["mesure", "encodage", "inconnu"]


class DebitCamera(BaseModel):
    id: int
    nom: str
    active: bool
    enregistrement: bool
    etat_enregistrement: EtatEnregistrement
    debit_o_s: int | None
    source_debit: SourceDebit
    # Début du plus ancien Segment conservé ; `None` : aucun.
    plus_ancien_segment: datetime | None


class DebitsEcriture(BaseModel):
    cameras: list[DebitCamera]
    debit_enregistrement_o_s: int | None
    debit_projection_o_s: int | None
    tenue_enregistrement_s: float | None
    tenue_projection_s: float | None
    conservation_s: int
    tenue_enregistrement_ok: bool | None
    tenue_projection_ok: bool | None


def lire(racine: Path, base: Session, libre_o: int) -> DebitsEcriture:
    """Débits par Caméra, agrégats (ON / projection actives) et tenue vs Conservation."""
    maintenant = time.time()
    cameras_lues: list[DebitCamera] = []
    for camera in base.scalars(select(Camera).order_by(Camera.id)):
        lue = CameraLue.depuis(camera, racine)
        debit_o_s, source = _debit_camera(camera, racine, maintenant)
        cameras_lues.append(
            DebitCamera(
                id=lue.id,
                nom=lue.nom,
                active=lue.active,
                enregistrement=lue.enregistrement,
                etat_enregistrement=lue.etat_enregistrement,
                debit_o_s=debit_o_s,
                source_debit=source,
                plus_ancien_segment=segments_fermes.debut_plus_ancien(racine, camera.id),
            )
        )

    en_cours = [c for c in cameras_lues if c.enregistrement]
    actives = [c for c in cameras_lues if c.active]
    debit_enr = _agregat(en_cours)
    debit_proj = _agregat(actives)
    conservation_s = reglages_site.conservation_h(base) * 3600
    tenue_enr, ok_enr = _tenue(libre_o, debit_enr, conservation_s, jeu_vide=len(en_cours) == 0)
    tenue_proj, ok_proj = _tenue(libre_o, debit_proj, conservation_s, jeu_vide=len(actives) == 0)

    return DebitsEcriture(
        cameras=cameras_lues,
        debit_enregistrement_o_s=debit_enr,
        debit_projection_o_s=debit_proj,
        tenue_enregistrement_s=tenue_enr,
        tenue_projection_s=tenue_proj,
        conservation_s=conservation_s,
        tenue_enregistrement_ok=ok_enr,
        tenue_projection_ok=ok_proj,
    )


def _debit_camera(camera: Camera, racine: Path, maintenant: float) -> tuple[int | None, SourceDebit]:
    dossier = racine / chemin_flux(camera.id)
    mesure = _mesurer(dossier, maintenant)
    if mesure is not None:
        return mesure, "mesure"
    encodage = _depuis_encodage(camera.debit_encodage_kbit_s)
    if encodage is not None:
        return encodage, "encodage"
    return None, "inconnu"


def _mesurer(dossier: Path, maintenant: float) -> int | None:
    """Somme des tailles des fichiers touchés dans la fenêtre / durée d'observation réelle.

    Si l'enregistrement vient de démarrer, on divise par le temps écoulé depuis le plus
    ancien fichier de la fenêtre (plancher 1 s), pas par la fenêtre pleine — sinon le
    débit est sous-estimé jusqu'à ce que la fenêtre soit remplie.
    """
    if not dossier.is_dir():
        return None
    seuil = maintenant - FENETRE_MESURE_S
    total = 0
    plus_ancien: float | None = None
    try:
        for chemin in dossier.rglob("*"):
            if not chemin.is_file():
                continue
            try:
                stats = chemin.stat()
            except OSError:
                continue
            if stats.st_mtime >= seuil:
                total += stats.st_size
                plus_ancien = stats.st_mtime if plus_ancien is None else min(plus_ancien, stats.st_mtime)
    except OSError:
        return None
    if plus_ancien is None:
        return None
    duree_s = max(1, min(FENETRE_MESURE_S, int(maintenant - plus_ancien) or 1))
    return total // duree_s


def _depuis_encodage(kbit_s: int | None) -> int | None:
    if kbit_s is None or kbit_s <= 0:
        return None
    return kbit_s * 1000 // 8


def _agregat(cameras: list[DebitCamera]) -> int | None:
    """Somme des débits connus. Jeu vide → 0. Toutes inconnues → None (les connues restent sommées)."""
    if not cameras:
        return 0
    connus = [c.debit_o_s or 0 for c in cameras if c.source_debit != "inconnu"]
    if not connus:
        return None
    return sum(connus)


def _tenue(
    libre_o: int, debit_o_s: int | None, conservation_s: int, *, jeu_vide: bool
) -> tuple[float | None, bool | None]:
    """Place libre / débit → secondes ; confronté à la Conservation. Jeu vide : OK (rien n'écrit)."""
    if jeu_vide:
        return None, True
    if debit_o_s is None:
        return None, None
    if debit_o_s == 0:
        return None, True
    tenue = libre_o / debit_o_s
    return tenue, tenue >= conservation_s
