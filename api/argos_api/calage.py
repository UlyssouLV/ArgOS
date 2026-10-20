"""Calage et vérification des Caméras sur le Serveur de temps du Site (docs/adr/0014-serveur-de-temps-du-site.md).

Chaque Caméra active est calée par ONVIF sans rien demander, même si elle visait un autre serveur : toutes en fond à
chaque changement de l'Heure du Site. Elle est vérifiée à son ajout (avant la réponse), toutes les heures et sur
« Vérifier maintenant » : son Horloge est relue, et recalée seulement si elle n'est plus calée (mode NTP, Serveur de
temps du Site, fuseau du Site) ; une Caméra calée qui s'écarte de plus de `ECART_SIGNALE_S` est signalée, sans rien
de plus. Le résultat de chaque Caméra (état, écart mesuré, date) est retenu. Un échec (pas d'ONVIF, ONVIF en clair non
accepté, caméra injoignable) est retenu et journalisé, jamais remonté : il ne bloque ni l'ajout ni les autres Caméras.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from argos_api import cameras, fuseaux, heure_site, onvif
from argos_api.cameras import EtatHorloge

# Caméras calées ou vérifiées en même temps : une caméra muette n'attend pas les autres.
CALAGES_SIMULTANES = 4
# Écart (secondes) au-delà duquel une Caméra pourtant calée est signalée.
ECART_SIGNALE_S = 2
# Une Caméra sans ONVIF, ou dont l'ONVIF en clair n'est pas accordé, se règle à la main.
CODES_SANS_ONVIF = ("sans_onvif", "en_clair_non_accepte")

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
        """Cale une Caméra active sans la relire d'abord, sans jamais lever."""
        self._traiter(id_camera, forcer=True)

    def verifier(self, id_camera: int) -> None:
        """Relit l'Horloge d'une Caméra active et la recale si elle n'est plus calée, sans jamais lever."""
        self._traiter(id_camera, forcer=False)

    def caler_toutes(self) -> None:
        """Cale en fond toutes les Caméras actives ; rend la main aussitôt."""
        for id_camera in self._actives():
            self._fond.submit(self.caler, id_camera)

    def verifier_toutes(self) -> None:
        """Vérifie toutes les Caméras actives, `CALAGES_SIMULTANES` à la fois ; rend la main quand toutes le sont."""
        list(self._fond.map(self.verifier, self._actives()))

    def arreter(self) -> None:
        self._fond.shutdown(wait=False, cancel_futures=True)

    def _actives(self) -> list[int]:
        with self._ouvrir_base() as base:
            return cameras.ids_actives(base)

    def _traiter(self, id_camera: int, forcer: bool) -> None:
        adresse = self._adresse
        if adresse is None:
            journal.warning(
                "Calage : Caméra %s non calée, adresse du Serveur de temps du Site inconnue "
                "(ARGOS_RESEAU_CAMERAS_TEMPS_IP ou MTX_WEBRTCADDITIONALHOSTS)",
                id_camera,
            )
            return
        with self._ouvrir_base() as base:
            fuseau = heure_site.lire(base, self._fuseau_hote).fuseau
            try:
                etat, horloge = self._caler_si_besoin(base, id_camera, adresse, fuseaux.posix(fuseau), forcer)
            except cameras.CameraIntrouvable:
                return
            except onvif.ErreurOnvif as erreur:
                journal.info("Calage : Caméra %s non vérifiée (%s)", id_camera, erreur.code)
                etat, horloge = ("sans_onvif" if erreur.code in CODES_SANS_ONVIF else "echec"), None
            ecart_s = horloge.ecart_s if horloge is not None else None
            cameras.retenir_horloge(base, id_camera, etat, ecart_s, self._maintenant())
        if horloge is not None:
            journal.info(
                "Calage : Caméra %s %s (Serveur de temps %s, fuseau %s, écart %.1f s)",
                id_camera, etat, adresse, fuseau, horloge.ecart_s,
            )

    def _caler_si_besoin(
        self, base: Session, id_camera: int, adresse: str, fuseau_posix: str, forcer: bool
    ) -> tuple[EtatHorloge, onvif.Horloge]:
        if not forcer:
            horloge = cameras.lire_horloge(base, id_camera, self._maintenant)
            if (horloge.mode, horloge.serveur_ntp, horloge.fuseau_posix) == ("ntp", adresse, fuseau_posix):
                return ("ecart" if abs(horloge.ecart_s) > ECART_SIGNALE_S else "calee"), horloge
        horloge = cameras.caler(base, id_camera, self._maintenant, adresse, fuseau_posix)
        return "recalee", horloge
