"""Surveillance des Caméras actives : un tour les sonde en parallèle et enregistre leur état.

Après une sonde réussie, la MAC lue à l'adresse de la Caméra dit si c'est bien son Appareil qui répond :
une autre MAC la met `offline` (`autre_appareil`), et le pont cesse de la relayer jusqu'au retour de la bonne.
Le codec lu par une sonde `online` remplace celui de la Caméra s'il a changé ; une sonde qui n'en lit pas le garde.
"""

import logging

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TypedDict

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from argos_api.modeles import AUTRE_APPAREIL, Camera, RaisonEtat
from argos_api.sonde import Sondage

journal = logging.getLogger(__name__)

Sonde = Callable[[str, float], Sondage]
# MAC de l'Appareil qui répond à l'hôte d'une URL RTSP, lue juste après la sonde ; `None` si illisible.
LireMac = Callable[[str], str | None]


class ColonnesApresSonde(TypedDict, total=False):
    """Colonnes d'une Caméra à réécrire après sa sonde ; une colonne absente reste inchangée."""

    etat: str
    raison_etat: RaisonEtat | None
    mac: str
    codec: str


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
                select(Camera.id, Camera.url_rtsp, Camera.mac, Camera.raison_etat, Camera.codec).where(Camera.active)
            ).all()
        if not cibles:
            return

        def sonder(cible) -> tuple[Sondage, str | None]:
            # La connexion de la sonde vient de remplir la table de voisinage.
            sondage = self._sonde(cible.url_rtsp, self._delai)
            return sondage, self._lire_mac(cible.url_rtsp) if sondage.en_ligne else None

        with ThreadPoolExecutor(max_workers=len(cibles)) as sondes:
            etats = list(zip(cibles, sondes.map(sonder, cibles), strict=True))
        verifie_le = self._horloge()
        codecs_changes = []
        with self._ouvrir_base() as base:
            for cible, (sondage, mac_lue) in etats:
                colonnes = _colonnes_apres_sonde(sondage.en_ligne, cible.mac, cible.raison_etat, mac_lue)
                # Seulement de son propre Appareil (`online`) : celui d'un autre Appareil à son adresse n'est pas le sien.
                if colonnes["etat"] == "online" and sondage.codec is not None and sondage.codec != cible.codec:
                    colonnes["codec"] = sondage.codec
                # Seulement si l'URL sondée et la MAC lue avant sont toujours les siennes, et la Caméra toujours
                # active : un changement pendant la sonde (remis à unknown, ou Détection) ne doit pas être écrasé.
                ecrite = base.execute(
                    update(Camera)
                    .where(
                        Camera.id == cible.id,
                        Camera.url_rtsp == cible.url_rtsp,
                        Camera.mac.is_not_distinct_from(cible.mac),
                        Camera.active,
                    )
                    .values(**colonnes, etat_verifie_le=verifie_le)
                )
                if "codec" in colonnes and ecrite.rowcount:
                    codecs_changes.append((cible.id, cible.codec, sondage.codec))
            base.commit()
        for id_camera, ancien, nouveau in codecs_changes:
            journal.info("codec de la Caméra %s : %s → %s", id_camera, ancien, nouveau)


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
