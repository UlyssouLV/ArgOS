"""Surveillance des Caméras actives : un tour les sonde en parallèle et enregistre leur état.

Après une sonde réussie, la MAC lue à l'adresse de la Caméra dit si c'est bien son Appareil qui répond :
une autre MAC la met `offline` (`autre_appareil`), et le pont cesse de la relayer jusqu'au retour de la bonne.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TypedDict

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from argos_api.modeles import AUTRE_APPAREIL, Camera, RaisonEtat

Sonde = Callable[[str, float], bool]
# MAC de l'Appareil qui répond à l'hôte d'une URL RTSP, lue juste après la sonde ; `None` si illisible.
LireMac = Callable[[str], str | None]


class ColonnesApresSonde(TypedDict, total=False):
    """Colonnes d'une Caméra à réécrire après sa sonde ; une colonne absente reste inchangée."""

    etat: str
    raison_etat: RaisonEtat | None
    mac: str


class Surveillance:
    def __init__(
        self,
        ouvrir_base: Callable[[], Session],
        sonde: Sonde,
        lire_mac: LireMac,
        delai: float,
        horloge: Callable[[], datetime],
    ) -> None:
        self._ouvrir_base = ouvrir_base
        self._sonde = sonde
        self._lire_mac = lire_mac
        self._delai = delai
        self._horloge = horloge

    def sonder_tout(self) -> None:
        with self._ouvrir_base() as base:
            cibles = base.execute(
                select(Camera.id, Camera.url_rtsp, Camera.mac, Camera.raison_etat).where(Camera.active)
            ).all()
        if not cibles:
            return

        def sonder(cible) -> tuple[bool, str | None]:
            # La connexion de la sonde vient de remplir la table de voisinage.
            en_ligne = self._sonde(cible.url_rtsp, self._delai)
            return en_ligne, self._lire_mac(cible.url_rtsp) if en_ligne else None

        with ThreadPoolExecutor(max_workers=len(cibles)) as sondes:
            etats = list(zip(cibles, sondes.map(sonder, cibles), strict=True))
        verifie_le = self._horloge()
        with self._ouvrir_base() as base:
            for cible, (en_ligne, mac_lue) in etats:
                # Seulement si l'URL sondée et la MAC lue avant sont toujours les siennes, et la Caméra toujours
                # active : un changement pendant la sonde (remis à unknown, ou Détection) ne doit pas être écrasé.
                base.execute(
                    update(Camera)
                    .where(
                        Camera.id == cible.id,
                        Camera.url_rtsp == cible.url_rtsp,
                        Camera.mac.is_not_distinct_from(cible.mac),
                        Camera.active,
                    )
                    .values(
                        **_colonnes_apres_sonde(en_ligne, cible.mac, cible.raison_etat, mac_lue),
                        etat_verifie_le=verifie_le,
                    )
                )
            base.commit()


def _colonnes_apres_sonde(
    en_ligne: bool, mac: str | None, raison: str | None, mac_lue: str | None
) -> ColonnesApresSonde:
    """État, raison et MAC après une sonde. MAC illisible, ou sonde échouée : MAC et raison inchangées."""
    if not en_ligne:
        # Personne ne répond : rien ne dit que la bonne MAC est revue, l'autre Appareil reste supposé là.
        return {"etat": "offline"}
    if mac_lue is None:
        return {"etat": "offline" if raison == AUTRE_APPAREIL else "online"}
    if mac is not None and mac_lue != mac:
        return {"etat": "offline", "raison_etat": AUTRE_APPAREIL}
    return {"etat": "online", "raison_etat": None, "mac": mac_lue}
