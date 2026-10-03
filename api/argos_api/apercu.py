"""Aperçu d'un essai : un seul pour le Site, jamais ouvert pour rien.

Retiré à l'ajout de la Caméra, à l'annulation, au remplacement par un nouvel essai, ou sans
renouvellement pendant le délai d'expiration (onglet fermé). Au démarrage de l'API, les chemins
`apercu-*` laissés dans MediaMTX par une instance précédente sont retirés.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import TypeVar

from argos_api import essai
from argos_api.pont import Pont

journal = logging.getLogger(__name__)

T = TypeVar("T")


class AucunApercu(Exception):
    """Aucun essai au Flux trouvé en cours : jamais ouvert, retiré ou expiré."""


class EssaiAnnule(Exception):
    """L'essai a été annulé pendant la recherche du Flux : son Aperçu n'est pas ouvert."""


@dataclass
class _Ouvert:
    resultat: essai.Resultat
    apercu: str
    # Selon `horloge` : au-delà, l'Aperçu est retiré.
    echeance: float


class Apercus:
    def __init__(self, pont: Pont, expiration_s: float, horloge: Callable[[], float] = monotonic) -> None:
        self._pont = pont
        self._expiration_s = expiration_s
        self._horloge = horloge
        self._verrou = threading.Lock()
        self._ouvert: _Ouvert | None = None
        # Change à chaque annulation : un essai en cours sait qu'il a été annulé.
        self._generation = 0
        self._orphelins_retires = False

    def debuter(self) -> int:
        """Retire l'Aperçu en cours avant un nouvel essai ; le jeton renvoyé sert à `ouvrir`."""
        with self._verrou:
            self._retirer()
            return self._generation

    def ouvrir(self, generation: int, resultat: essai.Resultat) -> str:
        """Ouvre l'Aperçu d'un Flux trouvé. Lève `EssaiAnnule`, ou `OSError` si MediaMTX le refuse."""
        with self._verrou:
            if generation != self._generation:
                raise EssaiAnnule
            apercu = self._pont.ouvrir_apercu(resultat.url)
            self._ouvert = _Ouvert(resultat, apercu, self._horloge() + self._expiration_s)
            return apercu

    def annuler(self) -> None:
        """Idempotent ; annule aussi l'essai en cours de recherche."""
        with self._verrou:
            self._generation += 1
            self._retirer()

    def renouveler(self) -> None:
        with self._verrou:
            self._ouvert_valide().echeance = self._horloge() + self._expiration_s

    def ajouter(self, creer: Callable[[str], T]) -> T:
        """`creer` reçoit l'URL du Flux (identifiants compris) ; s'il lève, l'Aperçu reste ouvert."""
        with self._verrou:
            camera = creer(self._ouvert_valide().resultat.url)
            self._retirer()
            return camera

    def entretenir(self) -> None:
        """Tour de fond : retire l'Aperçu expiré, puis, une fois, les orphelins d'une instance précédente."""
        with self._verrou:
            self._expirer()
            if not self._orphelins_retires:
                self._pont.retirer_apercus(sauf=self._ouvert.apercu if self._ouvert else None)
                self._orphelins_retires = True

    def _ouvert_valide(self) -> _Ouvert:
        self._expirer()
        if self._ouvert is None:
            raise AucunApercu
        return self._ouvert

    def _expirer(self) -> None:
        if self._ouvert is not None and self._horloge() >= self._ouvert.echeance:
            journal.info("Aperçu %s expiré sans renouvellement : retiré", self._ouvert.apercu)
            self._retirer()

    def _retirer(self) -> None:
        if self._ouvert is not None:
            self._pont.retirer_apercu(self._ouvert.apercu)
            self._ouvert = None
