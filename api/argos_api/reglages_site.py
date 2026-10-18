"""Réglages globaux du Site : Conservation des Segments (ADR 0012)."""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from argos_api.modeles import ReglagesSite

CONSERVATION_MIN = 1
CONSERVATION_MAX = 24
CONSERVATION_DEFAUT = 1
ID_UNIQUE = 1


class ReglagesSiteLus(BaseModel):
    conservation_h: int


class ModificationReglagesSite(BaseModel):
    conservation_h: int = Field(ge=CONSERVATION_MIN, le=CONSERVATION_MAX)


def lire(base: Session) -> ReglagesSiteLus:
    return ReglagesSiteLus(conservation_h=_ligne(base).conservation_h)


def modifier(base: Session, modification: ModificationReglagesSite) -> ReglagesSiteLus:
    ligne = _ligne(base)
    ligne.conservation_h = modification.conservation_h
    base.commit()
    return ReglagesSiteLus(conservation_h=ligne.conservation_h)


def conservation_h(base: Session) -> int:
    """Heures de Conservation courantes, pour la réconciliation du pont."""
    return _ligne(base).conservation_h


def _ligne(base: Session) -> ReglagesSite:
    ligne = base.get(ReglagesSite, ID_UNIQUE)
    if ligne is None:
        ligne = ReglagesSite(id=ID_UNIQUE, conservation_h=CONSERVATION_DEFAUT)
        base.add(ligne)
        base.commit()
        base.refresh(ligne)
    return ligne
