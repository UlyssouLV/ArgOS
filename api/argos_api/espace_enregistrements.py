"""Espace disque du volume des enregistrements (ADR 0012)."""

import os
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from argos_api import reglages_site


class EspaceEnregistrements(BaseModel):
    total_o: int
    libre_o: int
    utilise_o: int
    sous_seuil: bool


def lire(racine: Path, base: Session) -> EspaceEnregistrements:
    """Total / libre / utilisé du volume monté ; `sous_seuil` si libre < Seuil de place disque."""
    stats = os.statvfs(racine)
    total = stats.f_frsize * stats.f_blocks
    libre = stats.f_frsize * stats.f_bavail
    return EspaceEnregistrements(
        total_o=total,
        libre_o=libre,
        utilise_o=total - libre,
        sous_seuil=libre < reglages_site.seuil_octets_libres(base),
    )
