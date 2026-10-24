"""Heure du Site (docs/adr/0014-serveur-de-temps-du-site.md) : source de l'heure que suit `temps` et fuseau du Site,
réglés une fois pour toutes les Caméras."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from argos_api import fuseaux, reglages_site
from argos_api.serveur_de_temps import EtatServi, SourceUtilisee

# `ntp` : le serveur NTP externe choisi, repli sur l'horloge du serveur s'il est injoignable ; `horloge_serveur` :
# l'horloge du serveur seule.
Source = Literal["ntp", "horloge_serveur"]
# Un nom DNS ou une IPv4, rien d'autre : la source finit dans la configuration de chrony.
MOTIF_SERVEUR_NTP = r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$"


@dataclass(frozen=True)
class HeureDuSite:
    source: Source
    serveur_ntp: str
    # Fuseau IANA du Site ; celui de l'hôte tant que l'Administrateur n'en a pas choisi.
    fuseau: str
    fuseau_de_l_hote: bool

    @property
    def source_suivie(self) -> str | None:
        """Ce que `temps` doit suivre : le serveur NTP, ou `None` pour l'horloge du serveur."""
        return self.serveur_ntp if self.source == "ntp" else None


class HeureDuSiteLue(BaseModel):
    source: Source
    serveur_ntp: str
    fuseau: str
    fuseau_de_l_hote: bool
    # Lus sur temps à chaque appel, comme une Caméra les voit.
    source_utilisee: SourceUtilisee
    reference: str | None
    heure: datetime | None
    # Adresse du Serveur de temps du Site annoncée aux Caméras ; `None` : inconnue, aucune Caméra n'est calée.
    adresse_serveur_de_temps: str | None
    # Base des fuseaux d'où viennent les décalages envoyés aux Caméras, relue à chaque appel.
    base_des_fuseaux: fuseaux.BaseDesFuseaux


class ModificationHeureDuSite(BaseModel):
    """Champs partiels : seuls ceux envoyés changent."""

    source: Source | None = None
    serveur_ntp: str | None = Field(default=None, pattern=MOTIF_SERVEUR_NTP)
    fuseau: str | None = None

    @field_validator("fuseau")
    @classmethod
    def fuseau_connu(cls, fuseau: str | None) -> str | None:
        if fuseau is not None and not fuseaux.connu(fuseau):
            raise ValueError("Fuseau inconnu.")
        return fuseau

    @model_validator(mode="after")
    def au_moins_un_champ(self) -> "ModificationHeureDuSite":
        if self.source is None and self.serveur_ntp is None and self.fuseau is None:
            raise ValueError("Au moins un réglage de l'Heure du Site est requis.")
        return self


def lire(base: Session, fuseau_hote: str) -> HeureDuSite:
    ligne = reglages_site.ligne_du_site(base)
    return HeureDuSite(
        source="horloge_serveur" if ligne.heure_source == "horloge_serveur" else "ntp",
        serveur_ntp=ligne.heure_serveur_ntp,
        fuseau=ligne.fuseau or fuseau_hote,
        fuseau_de_l_hote=ligne.fuseau is None,
    )


def modifier(base: Session, modification: ModificationHeureDuSite, fuseau_hote: str) -> HeureDuSite:
    ligne = reglages_site.ligne_du_site(base)
    if modification.source is not None:
        ligne.heure_source = modification.source
    if modification.serveur_ntp is not None:
        ligne.heure_serveur_ntp = modification.serveur_ntp
    if modification.fuseau is not None:
        ligne.fuseau = modification.fuseau
    base.commit()
    return lire(base, fuseau_hote)


def avec_ce_que_sert_temps(reglage: HeureDuSite, servi: EtatServi, adresse: str | None) -> HeureDuSiteLue:
    """L'Heure du Site réglée, avec ce que `temps` sert vraiment aux Caméras et l'adresse qui leur est annoncée."""
    return HeureDuSiteLue(
        source=reglage.source,
        serveur_ntp=reglage.serveur_ntp,
        fuseau=reglage.fuseau,
        fuseau_de_l_hote=reglage.fuseau_de_l_hote,
        source_utilisee=servi.source_utilisee,
        reference=servi.reference,
        heure=servi.heure,
        adresse_serveur_de_temps=adresse,
        base_des_fuseaux=fuseaux.base(),
    )
