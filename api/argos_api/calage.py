"""Vérification des Caméras : Mise à l'heure et calage sur le Serveur de temps du Site
(docs/adr/0014-serveur-de-temps-du-site.md, docs/adr/0015-mise-a-l-heure-a-chaque-verification.md).

Chaque Caméra active est vérifiée à son ajout (avant la réponse), à chaque changement de l'Heure du Site (toutes, en
fond), toutes les heures et sur « Vérifier maintenant », par une seule procédure sans condition : lire l'heure que sert
`temps` (en NTP) ; lire l'Horloge de la Caméra (la dérive) ; y pousser cette heure en mode manuel, au fuseau du Site ;
la caler (serveur NTP = le Site, mode NTP, fuseau du Site), même si elle visait un autre serveur ; relire son Horloge
(l'écart). Le fuseau envoyé est le décalage du moment du fuseau du Site, sans règles d'heure d'été ; une vérification
de toutes les Caméras a aussi lieu à chaque changement d'heure (`changement_d_heure`). Dérive et écart se mesurent
contre l'heure de `temps`, jamais contre l'horloge de l'OS. L'écart relu et le décalage du fuseau relu décident de
l'état : `a_l_heure` si l'écart ne dépasse pas `ECART_SIGNALE_S` et si le décalage relu est celui du Site, `ecart`
sinon (journalisé), même si la Caméra a refusé l'heure poussée (journalisé). `temps` muet : rien n'est poussé ni
mesuré, la Caméra est calée seule et marquée `echec`. Le résultat de chaque Caméra (état, dérive, écart, date) est
retenu. Un échec ONVIF (pas d'ONVIF, ONVIF en clair non accepté, caméra injoignable) est retenu et journalisé, jamais
remonté : il ne bloque ni l'ajout ni les autres Caméras.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

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
        # Base des fuseaux mise à jour par l'OS depuis la vérification précédente : prise maintenant.
        fuseaux.base()
        with self._ouvrir_base() as base:
            fuseau = heure_site.lire(base, self._fuseau_hote).fuseau
            posix = fuseaux.posix_du_moment(fuseau, self._maintenant())
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
                    decalage_juste = _decalage_juste(id_camera, mise.apres.fuseau_posix, posix)
                    etat = "ecart" if abs(ecart_s) > ECART_SIGNALE_S or not decalage_juste else "a_l_heure"
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


def _decalage_juste(id_camera: int, relu: str | None, envoye: str) -> bool:
    """Le fuseau relu sur la Caméra a le décalage de celui envoyé : la date qu'elle incruste est l'heure locale du
    Site. Sinon, journalise pourquoi elle n'est pas à l'heure."""
    attendu = fuseaux.decalage(envoye)
    lu = fuseaux.decalage(relu) if relu else None
    if lu == attendu:
        return True
    journal.warning(
        "Calage : Caméra %s en écart : fuseau relu %s (%s), le Site envoie %s (%s)",
        id_camera, relu, _texte_decalage(lu), envoye, _texte_decalage(attendu),
    )
    return False


def _texte_decalage(decalage: timedelta | None) -> str:
    if decalage is None:
        return "décalage illisible"
    signe = "-" if decalage < timedelta() else "+"
    heures, reste = divmod(int(abs(decalage).total_seconds()), 3600)
    return f"UTC{signe}{heures:02d}:{reste // 60:02d}"
