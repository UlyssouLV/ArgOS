"""Réglages globaux du Site : Conservation des Segments et Seuil de place disque (ADR 0012)."""

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from argos_api.modeles import ReglagesSite

CONSERVATION_MIN = 1
CONSERVATION_MAX = 24
CONSERVATION_DEFAUT = 1
SEUIL_MIN = 104_857_600  # 100 Mo
SEUIL_DEFAUT = 1_073_741_824  # 1 Go
ID_UNIQUE = 1


class ReglagesSiteLus(BaseModel):
    conservation_h: int
    seuil_octets_libres: int


class ModificationReglagesSite(BaseModel):
    """Champs partiels : seuls ceux envoyés changent."""

    conservation_h: int | None = Field(default=None, ge=CONSERVATION_MIN, le=CONSERVATION_MAX)
    seuil_octets_libres: int | None = Field(default=None, ge=SEUIL_MIN)

    @model_validator(mode="after")
    def au_moins_un_champ(self) -> "ModificationReglagesSite":
        if self.conservation_h is None and self.seuil_octets_libres is None:
            raise ValueError("Au moins un réglage Site est requis.")
        return self


def lire(base: Session) -> ReglagesSiteLus:
    return _lus(_ligne(base))


def modifier(base: Session, modification: ModificationReglagesSite) -> ReglagesSiteLus:
    ligne = _ligne(base)
    for champ, valeur in modification.model_dump(exclude_unset=True).items():
        if valeur is not None:
            setattr(ligne, champ, valeur)
    base.commit()
    return _lus(ligne)


def conservation_h(base: Session) -> int:
    """Heures de Conservation courantes, pour la réconciliation du pont."""
    return _ligne(base).conservation_h


def seuil_octets_libres(base: Session) -> int:
    """Seuil de place disque courant, en octets libres."""
    return _ligne(base).seuil_octets_libres


def _lus(ligne: ReglagesSite) -> ReglagesSiteLus:
    return ReglagesSiteLus(
        conservation_h=ligne.conservation_h,
        seuil_octets_libres=ligne.seuil_octets_libres,
    )


def _ligne(base: Session) -> ReglagesSite:
    ligne = base.get(ReglagesSite, ID_UNIQUE)
    if ligne is None:
        ligne = ReglagesSite(
            id=ID_UNIQUE,
            conservation_h=CONSERVATION_DEFAUT,
            seuil_octets_libres=SEUIL_DEFAUT,
        )
        base.add(ligne)
        base.commit()
        base.refresh(ligne)
    return ligne
