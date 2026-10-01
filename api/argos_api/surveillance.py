"""Surveillance des Caméras actives : boucle de fond qui les sonde en parallèle et enregistre leur état."""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from argos_api.modeles import Camera

journal = logging.getLogger(__name__)

Sonde = Callable[[str, float], bool]


class Surveillance:
    def __init__(
        self,
        ouvrir_base: Callable[[], Session],
        sonde: Sonde,
        intervalle: float,
        delai: float,
        horloge: Callable[[], datetime],
    ) -> None:
        self._ouvrir_base = ouvrir_base
        self._sonde = sonde
        self._intervalle = intervalle
        self._delai = delai
        self._horloge = horloge
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._tourner, name="surveillance-cameras", daemon=True)

    def demarrer(self) -> None:
        self._fil.start()

    def arreter(self) -> None:
        self._arret.set()
        self._fil.join()

    def _tourner(self) -> None:
        while not self._arret.is_set():
            try:
                self.sonder_tout()
            except Exception:
                # Base indisponible un instant, par exemple : la boucle ne meurt pas, elle réessaie.
                journal.exception("Sonde des Caméras interrompue")
            self._arret.wait(self._intervalle)

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
