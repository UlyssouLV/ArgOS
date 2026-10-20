"""Calage des Caméras sur le Serveur de temps du Site (docs/adr/0014-serveur-de-temps-du-site.md).

Chaque Caméra active est calée par ONVIF sans rien demander, même si elle visait un autre serveur : à son ajout (avant
la réponse), et toutes en fond à chaque changement de l'Heure du Site. Un échec (pas d'ONVIF, ONVIF en clair non
accepté, caméra injoignable) est journalisé, jamais remonté : il ne bloque ni l'ajout ni les autres Caméras.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from argos_api import cameras, fuseaux, heure_site, onvif

# Caméras calées en même temps au changement de l'Heure du Site : une caméra muette n'attend pas les autres.
CALAGES_SIMULTANES = 4

journal = logging.getLogger("argos_api.calage")


class Calage:
    def __init__(
        self,
        ouvrir_base: Callable[[], Session],
        maintenant: Callable[[], datetime],
        adresse: str | None,
        fuseau_hote: str,
    ) -> None:
        """`adresse` : celle du Serveur de temps du Site annoncée aux Caméras ; `None`, aucune n'est calée."""
        self._ouvrir_base = ouvrir_base
        self._maintenant = maintenant
        self._adresse = adresse
        self._fuseau_hote = fuseau_hote
        self._fond = ThreadPoolExecutor(CALAGES_SIMULTANES, thread_name_prefix="calage")

    def caler(self, id_camera: int) -> None:
        """Cale une Caméra active, sans jamais lever."""
        if self._adresse is None:
            journal.warning(
                "Calage : Caméra %s non calée, adresse du Serveur de temps du Site inconnue "
                "(ARGOS_RESEAU_CAMERAS_TEMPS_IP ou MTX_WEBRTCADDITIONALHOSTS)",
                id_camera,
            )
            return
        with self._ouvrir_base() as base:
            fuseau = heure_site.lire(base, self._fuseau_hote).fuseau
            try:
                horloge = cameras.caler(base, id_camera, self._maintenant, self._adresse, fuseaux.posix(fuseau))
            except cameras.CameraIntrouvable:
                return
            except onvif.ErreurOnvif as erreur:
                journal.info("Calage : Caméra %s non calée (%s)", id_camera, erreur.code)
                return
        journal.info(
            "Calage : Caméra %s calée sur %s, fuseau %s, écart %.1f s", id_camera, self._adresse, fuseau, horloge.ecart_s
        )

    def caler_toutes(self) -> None:
        """Cale en fond toutes les Caméras actives ; rend la main aussitôt."""
        with self._ouvrir_base() as base:
            actives = cameras.ids_actives(base)
        for id_camera in actives:
            self._fond.submit(self.caler, id_camera)

    def arreter(self) -> None:
        self._fond.shutdown(wait=False, cancel_futures=True)
