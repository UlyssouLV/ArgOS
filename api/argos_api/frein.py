"""Frein à la force brute sur la connexion : compteur global en mémoire, un seul compte.

Remis à zéro au redémarrage de l'API (dette consignée dans docs/securite.md).
"""

import threading
from collections.abc import Callable
from datetime import datetime, timedelta

ECHECS_MAX = 5
FENETRE = timedelta(minutes=15)
BLOCAGE = timedelta(minutes=15)


class TropDEchecs(Exception):
    """La connexion est bloquée : trop d'échecs récents."""


class FreinForceBrute:
    def __init__(self, horloge: Callable[[], datetime]) -> None:
        self._horloge = horloge
        self._verrou = threading.Lock()
        self._echecs: list[datetime] = []
        self._bloque_jusqua: datetime | None = None

    def essayer(self, essai: Callable[[], bool]) -> bool:
        """Lance `essai` et compte son échec ; lève TropDEchecs pendant un blocage, sans le lancer."""
        # Vérification et comptage sous le même verrou : des essais simultanés ne passent pas entre les deux.
        with self._verrou:
            maintenant = self._horloge()
            if self._bloque_jusqua is not None and maintenant < self._bloque_jusqua:
                raise TropDEchecs
            if essai():
                return True
            self._echecs = [t for t in self._echecs if maintenant - t < FENETRE] + [maintenant]
            if len(self._echecs) >= ECHECS_MAX:
                self._bloque_jusqua = maintenant + BLOCAGE
                self._echecs = []
            return False
