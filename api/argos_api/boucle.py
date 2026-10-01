"""Boucle de fond : un tour au démarrage, puis un tour par intervalle, jusqu'à l'arrêt de l'API."""

import logging
import threading
from collections.abc import Callable

journal = logging.getLogger(__name__)


class BoucleDeFond:
    def __init__(self, nom: str, tour: Callable[[], None], intervalle: float) -> None:
        self._nom = nom
        self._tour = tour
        self._intervalle = intervalle
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._tourner, name=nom, daemon=True)

    def demarrer(self) -> None:
        self._fil.start()

    def arreter(self) -> None:
        self._arret.set()
        self._fil.join()

    def _tourner(self) -> None:
        while not self._arret.is_set():
            try:
                self._tour()
            except Exception:
                # Base ou MediaMTX indisponible un instant, par exemple : la boucle ne meurt pas, elle réessaie.
                journal.exception("Boucle %s : tour interrompu", self._nom)
            self._arret.wait(self._intervalle)
