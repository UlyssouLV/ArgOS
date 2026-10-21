"""Vérification des Caméras : Mise à l'heure et calage sur le Serveur de temps du Site
(docs/adr/0014-serveur-de-temps-du-site.md, docs/adr/0015-mise-a-l-heure-a-chaque-verification.md).

Chaque Caméra active est vérifiée à son ajout (avant la réponse), à chaque changement de l'Heure du Site (toutes, en
fond), toutes les heures et sur « Vérifier maintenant », par une seule procédure sans condition : lire l'heure que sert
`temps` (en NTP) ; lire l'Horloge de la Caméra (la dérive) ; y pousser cette heure en mode manuel, au fuseau du Site ;
la caler (serveur NTP = le Site, mode NTP, fuseau du Site), même si elle visait un autre serveur ; relire son Horloge
(l'écart). Dérive et écart se mesurent contre l'heure de `temps`, jamais contre l'horloge de l'OS. L'écart relu
décide de l'état : `a_l_heure` jusqu'à `ECART_SIGNALE_S`, `ecart` au-delà, même si la Caméra a refusé l'heure poussée
(journalisé). `temps` muet : rien n'est poussé ni mesuré, la Caméra est calée seule et marquée `echec`. Le résultat de
chaque Caméra (état, dérive, écart, date) est retenu. Un échec ONVIF (pas d'ONVIF, ONVIF en clair non accepté,
caméra injoignable) est retenu et journalisé, jamais remonté : il ne bloque ni l'ajout ni les autres Caméras.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from argos_api import cameras, fuseaux, heure_site, onvif
from argos_api.cameras import EtatHorloge

# Caméras vérifiées en même temps : une caméra muette n'attend pas les autres.
CALAGES_SIMULTANES = 4
# Écart relu (secondes) au-delà duquel une Caméra n'est pas à l'heure.
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
        heure_de_temps: Callable[[], Callable[[], datetime] | None],
    ) -> None:
        """`adresse` : celle du Serveur de temps du Site annoncée aux Caméras ; `None`, aucune n'est vérifiée.
        `heure_de_temps` : lit l'heure que sert `temps`, horloge qui avance d'elle-même ; `None` s'il ne répond pas."""
        self._ouvrir_base = ouvrir_base
        self._maintenant = maintenant
        self._adresse = adresse
        self._fuseau_hote = fuseau_hote
        self._heure_de_temps = heure_de_temps
        self._fond = ThreadPoolExecutor(CALAGES_SIMULTANES, thread_name_prefix="calage")

    def verifier(self, id_camera: int) -> None:
        """Met à l'heure et cale une Caméra active, puis retient le résultat, sans jamais lever."""
        adresse = self._adresse
        if adresse is None:
            journal.warning(
                "Calage : Caméra %s non vérifiée, adresse du Serveur de temps du Site inconnue "
                "(ARGOS_RESEAU_CAMERAS_TEMPS_IP ou MTX_WEBRTCADDITIONALHOSTS)",
                id_camera,
            )
            return
        reference = self._heure_de_temps()
        with self._ouvrir_base() as base:
            fuseau = heure_site.lire(base, self._fuseau_hote).fuseau
            posix = fuseaux.posix(fuseau)
            derive_s = ecart_s = None
            etat: EtatHorloge
            try:
                if reference is None:
                    cameras.caler(base, id_camera, self._maintenant, adresse, posix)
                    journal.warning(
                        "Calage : Caméra %s calée sans Mise à l'heure : Serveur de temps du Site injoignable",
                        id_camera,
                    )
                    etat = "echec"
                else:
                    mise = cameras.mettre_a_l_heure(base, id_camera, self._maintenant, reference, adresse, posix)
                    if mise.refusee:
                        journal.warning("Calage : Caméra %s : Mise à l'heure refusée, calée quand même", id_camera)
                    derive_s, ecart_s = mise.avant.ecart_s, mise.apres.ecart_s
                    etat = "ecart" if abs(ecart_s) > ECART_SIGNALE_S else "a_l_heure"
            except cameras.CameraIntrouvable:
                return
            except onvif.ErreurOnvif as erreur:
                journal.info("Calage : Caméra %s non vérifiée (%s)", id_camera, erreur.code)
                etat = "sans_onvif" if erreur.code in CODES_SANS_ONVIF else "echec"
            cameras.retenir_horloge(base, id_camera, etat, derive_s, ecart_s, self._maintenant())
        if ecart_s is not None:
            journal.info(
                "Calage : Caméra %s %s (Serveur de temps %s, fuseau %s, dérive %.1f s, écart %.1f s)",
                id_camera, etat, adresse, fuseau, derive_s, ecart_s,
            )

    def verifier_toutes_en_fond(self) -> None:
        """Vérifie en fond toutes les Caméras actives ; rend la main aussitôt."""
        for id_camera in self._actives():
            self._fond.submit(self.verifier, id_camera)

    def verifier_toutes(self) -> None:
        """Vérifie toutes les Caméras actives, `CALAGES_SIMULTANES` à la fois ; rend la main quand toutes le sont."""
        list(self._fond.map(self.verifier, self._actives()))

    def arreter(self) -> None:
        self._fond.shutdown(wait=False, cancel_futures=True)

    def _actives(self) -> list[int]:
        with self._ouvrir_base() as base:
            return cameras.ids_actives(base)
