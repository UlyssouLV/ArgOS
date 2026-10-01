"""Surveillance des Caméras actives : un tour les sonde en parallèle et enregistre leur état."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from argos_api.modeles import Camera

Sonde = Callable[[str, float], bool]


class Surveillance:
    def __init__(
        self,
        ouvrir_base: Callable[[], Session],
        sonde: Sonde,
        delai: float,
        horloge: Callable[[], datetime],
    ) -> None:
        self._ouvrir_base = ouvrir_base
        self._sonde = sonde
        self._delai = delai
        self._horloge = horloge

    def sonder_tout(self) -> None:
        with self._ouvrir_base() as base:
            cibles = base.execute(select(Camera.id, Camera.url_rtsp).where(Camera.active)).all()
        if not cibles:
            return
        with ThreadPoolExecutor(max_workers=len(cibles)) as sondes:
            resultats = sondes.map(lambda cible: self._sonde(cible.url_rtsp, self._delai), cibles)
            etats = list(zip(cibles, resultats, strict=True))
        verifie_le = self._horloge()
        with self._ouvrir_base() as base:
            for cible, en_ligne in etats:
                # Seulement si l'URL sondée est toujours la sienne et la Caméra toujours active :
                # un changement pendant la sonde a remis l'état à unknown, il ne doit pas être écrasé.
                base.execute(
                    update(Camera)
                    .where(Camera.id == cible.id, Camera.url_rtsp == cible.url_rtsp, Camera.active)
                    .values(etat="online" if en_ligne else "offline", etat_verifie_le=verifie_le)
                )
            base.commit()
