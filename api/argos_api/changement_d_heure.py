"""Vérification de toutes les Caméras actives à l'instant de chaque changement d'heure du fuseau du Site
(docs/adr/0015-mise-a-l-heure-a-chaque-verification.md, avenant).

Le Site envoie aux Caméras le décalage du moment de son fuseau, sans règles d'heure d'été : à chaque changement
d'heure, il leur envoie le nouveau. L'instant est recalculé après chaque changement et à chaque changement de fuseau
(`reprogrammer`). L'horloge est relue tous les `pas_s` au plus : un saut d'horloge ne fait pas manquer l'instant.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from argos_api import fuseaux

# Relecture de l'horloge au plus tard toutes les… (secondes).
PAS_S = 60

journal = logging.getLogger("argos_api.calage")


class VerificationAuChangementDHeure:
    def __init__(
        self,
        fuseau: Callable[[], str],
        maintenant: Callable[[], datetime],
        verifier_toutes: Callable[[], None],
        pas_s: float = PAS_S,
    ) -> None:
        """`fuseau` : lit le fuseau IANA du Site ; `verifier_toutes` : vérifie toutes les Caméras actives."""
        self._fuseau = fuseau
        self._maintenant = maintenant
        self._verifier_toutes = verifier_toutes
        self._pas_s = pas_s
        self._reveil = threading.Event()
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._tourner, name="changement-d-heure", daemon=True)
        # Instant de la prochaine vérification ; `None` : aucun changement d'heure prévu dans l'année.
        self.prevue: datetime | None = None

    def demarrer(self) -> None:
        self._fil.start()

    def reprogrammer(self) -> None:
        """Le fuseau du Site a changé : recalcule l'instant."""
        self._reveil.set()

    def arreter(self) -> None:
        self._arret.set()
        self._reveil.set()
        self._fil.join()

    def _tourner(self) -> None:
        while not self._arret.is_set():
            try:
                self.prevue = fuseaux.prochain_changement(self._fuseau(), self._maintenant())
            except Exception:
                # Base indisponible un instant, par exemple : réessaie au prochain pas.
                journal.exception("Changement d'heure : prochain instant non calculé")
                self.prevue = None
            while not self._reveil.wait(self._attente_s()):
                if self.prevue is None:
                    # Fuseau illisible, ou sans changement dans l'année : recalculé à chaque pas.
                    break
                if self._maintenant() >= self.prevue:
                    journal.info("Changement d'heure : vérification de toutes les Caméras actives")
                    self._verifier_toutes()
                    break
            self._reveil.clear()

    def _attente_s(self) -> float:
        """Jusqu'à l'instant prévu, `pas_s` au plus."""
        if self.prevue is None:
            return self._pas_s
        return max(0.0, min(self._pas_s, (self.prevue - self._maintenant()).total_seconds()))
