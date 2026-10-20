"""Caméras du Site : URL RTSP (validation, masquage, hôte et port) et règles de gestion."""

import logging
import os
import shutil
import socket
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from ipaddress import IPv4Address
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import SplitResult, unquote, urlsplit

from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from argos_api import onvif, voisinage
from argos_api.detection import Candidat
from argos_api.modeles import AUTRE_APPAREIL, Camera, RaisonEtat
from argos_api.pont import Relais, chemin_flux

PORT_RTSP = 554
MASQUE = "***"
# En dessous, le mot de passe d'une caméra est signalé comme court (à l'ajout, et en ONVIF en clair).
LONGUEUR_MOT_DE_PASSE_SUR = 12

Etat = Literal["unknown", "online", "offline"]
EtatEnregistrement = Literal["enregistre", "a_l_arret", "en_erreur"]
# Au-delà de 2 × recordSegmentDuration (1 m) : l'écriture a stagné alors que l'enregistrement est ON.
AGE_MAX_DERNIER_SEGMENT_S = 120.0

# Refus et décisions sur le Certificat de l'Appareil : id de Caméra et empreintes, jamais d'identifiant ni d'URL.
journal = logging.getLogger("argos_api.cameras")


class CameraIntrouvable(Exception):
    pass


class Doublon(Exception):
    """Le nom ou l'URL est déjà pris, y compris par une Caméra désactivée."""


class CameraActive(Exception):
    """Seule une Caméra désactivée peut être supprimée."""


class EnregistrementRefuse(Exception):
    """Une Caméra désactivée ne peut pas enregistrer."""


class CertificatNonPresente(Exception):
    """La caméra ne présente pas (ou plus) le Certificat de l'Appareil auquel l'Administrateur veut faire confiance."""


def _decouper(url: str) -> SplitResult:
    morceaux = urlsplit(url)
    if morceaux.scheme != "rtsp" or not morceaux.hostname:
        raise ValueError("URL RTSP attendue : rtsp://[utilisateur:motdepasse@]hote[:port]/chemin")
    morceaux.port  # Lève ValueError si le port n'est pas un nombre valide.
    return morceaux


def _valider(url: str) -> str:
    _decouper(url)
    return url


UrlRtsp = Annotated[str, AfterValidator(_valider)]


def masquer(url: str) -> str:
    """`rtsp://user:motdepasse@hote/...` → `rtsp://user:***@hote/...` ; sans mot de passe, inchangée."""
    morceaux = _decouper(url)
    if morceaux.password is None:
        return url
    utilisateur = morceaux.netloc.rpartition("@")[0].partition(":")[0]
    hote = morceaux.netloc.rpartition("@")[2]
    return morceaux._replace(netloc=f"{utilisateur}:{MASQUE}@{hote}").geturl()


class NouvelleCamera(BaseModel):
    nom: str = Field(min_length=1)
    url_rtsp: UrlRtsp
    emplacement: str | None = None


class ModificationCamera(BaseModel):
    """Champs partiels : seuls ceux envoyés changent ; `null` n'est accepté que pour `emplacement`."""

    nom: str = Field(None, min_length=1)
    url_rtsp: UrlRtsp = None
    emplacement: str | None = None
    active: bool = None
    enregistrement: bool = None


class CameraLue(BaseModel):
    id: int
    nom: str
    url_rtsp: str
    emplacement: str | None
    hote: str
    port: int
    active: bool
    etat: Etat
    etat_verifie_le: datetime | None
    raison_etat: RaisonEtat | None
    # Chemin MediaMTX qui relaie le Flux (docs/adr/0001-mediamtx-en-pont.md) ; aucun si désactivée.
    chemin_flux: str | None
    # MAC de l'Appareil, `aa:bb:cc:dd:ee:ff` ; `None` : inconnue. Jamais modifiable par l'Administrateur.
    mac: str | None
    # Nom d'encodage lu dans le SDP (`H264`, `H265`…) ; `None` : jamais lu. Jamais modifiable par l'Administrateur.
    codec: str | None
    # Port ONVIF trouvé par ArgOS à l'ouverture des Réglages ; `None` : jamais cherché. Jamais modifiable.
    port_onvif: int | None
    # Schéma de ce port, cherché avec lui.
    schema_onvif: onvif.Schema | None
    # L'Administrateur accepte l'ONVIF en clair (caméra sans HTTPS) ; depuis ses Réglages.
    onvif_en_clair_accepte: bool
    enregistrement: bool
    # Indicateur d'enregistrement : lecture du volume, pas de téléchargement des segments.
    etat_enregistrement: EtatEnregistrement
    dossier_enregistrement: str
    age_dernier_segment_s: float | None

    @classmethod
    def depuis(cls, camera: Camera, racine_enregistrements: Path) -> "CameraLue":
        morceaux = _decouper(camera.url_rtsp)
        etat_enregistrement, dossier, age = _indicateur_enregistrement(camera, racine_enregistrements)
        return cls(
            id=camera.id,
            nom=camera.nom,
            url_rtsp=masquer(camera.url_rtsp),
            emplacement=camera.emplacement,
            hote=morceaux.hostname,
            port=morceaux.port or PORT_RTSP,
            active=camera.active,
            etat=camera.etat,
            etat_verifie_le=camera.etat_verifie_le,
            raison_etat=camera.raison_etat,
            chemin_flux=chemin_flux(camera.id) if camera.active else None,
            mac=camera.mac,
            codec=camera.codec,
            port_onvif=camera.port_onvif,
            schema_onvif=camera.schema_onvif,
            onvif_en_clair_accepte=camera.onvif_en_clair_accepte,
            enregistrement=camera.enregistrement,
            etat_enregistrement=etat_enregistrement,
            dossier_enregistrement=dossier,
            age_dernier_segment_s=age,
        )


def lister(base: Session, racine_enregistrements: Path) -> list[CameraLue]:
    return [CameraLue.depuis(c, racine_enregistrements) for c in base.scalars(select(Camera).order_by(Camera.id))]


def _indicateur_enregistrement(camera: Camera, racine: Path) -> tuple[EtatEnregistrement, str, float | None]:
    """État, chemin du dossier `camera-<id>` et âge du dernier segment (lecture du volume)."""
    dossier = racine / chemin_flux(camera.id)
    chemin = dossier.as_posix()
    try:
        age = _age_dernier_segment(dossier)
        plein = os.statvfs(racine).f_bavail == 0
    except OSError:
        return "en_erreur", chemin, None
    if not camera.enregistrement:
        return "a_l_arret", chemin, age
    if plein or camera.etat == "offline" or (age is not None and age > AGE_MAX_DERNIER_SEGMENT_S):
        return "en_erreur", chemin, age
    return "enregistre", chemin, age


def _age_dernier_segment(dossier: Path) -> float | None:
    if not dossier.exists():
        return None
    if not dossier.is_dir():
        raise OSError("dossier d'enregistrement illisible")
    fichiers = [chemin for chemin in dossier.rglob("*") if chemin.is_file()]
    if not fichiers:
        return None
    return time.time() - max(chemin.stat().st_mtime for chemin in fichiers)


def relais_actifs(base: Session) -> dict[int, Relais]:
    """Relais de chaque Caméra active : URL RTSP stockée (mot de passe compris) et Enregistrement.

    Sans celles où un autre Appareil répond : son Flux ne doit jamais passer sous leur nom.
    """
    lignes = base.execute(
        select(Camera.id, Camera.url_rtsp, Camera.enregistrement).where(
            Camera.active, Camera.raison_etat.is_distinct_from(AUTRE_APPAREIL)
        )
    )
    return {id_camera: Relais(url, enregistrement) for id_camera, url, enregistrement in lignes}


def mac_a_l_adresse(url: str) -> str | None:
    """MAC de l'Appareil à l'IP de l'hôte de `url`, juste après lui avoir parlé ; `None` si illisible.

    Un hôte qui résout en plusieurs IP : on ne sait pas laquelle a répondu, `None`.
    """
    ips = [ip for ip, _ in _adresses(url)]
    return voisinage.mac_de(ips[0]) if len(ips) == 1 else None


class CameraCorrespondante(BaseModel):
    id: int
    nom: str


class Correspondance(BaseModel):
    """Caméra du Site rapprochée d'un essai ; `deja_configuree` : ajouter ce Flux ferait un doublon."""

    camera: CameraCorrespondante
    deja_configuree: bool


def correspondance_de_l_essai(
    base: Session, ip: IPv4Address, port: int, mac: str | None, chemin: str | None
) -> Correspondance | None:
    """Caméra (active ou désactivée) que l'essai de `ip:port` rejoint ; `None` : rien de connu.

    D'abord à la même IP résolue et au même port, comme la Détection : déjà configurée, la plus ancienne ; une
    Caméra d'un autre Appareil (MAC connues et différentes) est écartée, celui-ci a repris son adresse. Sinon,
    Flux trouvé (`chemin`) sur un Appareil connu : au même chemin, déjà configurée ; à un autre chemin, la plus
    ancienne de l'Appareil, ajout permis.
    """
    toutes = list(base.scalars(select(Camera).order_by(Camera.id)))
    a_l_adresse = next(
        (c for c in toutes if (ip, port) in _adresses(c.url_rtsp) and _meme_appareil_possible(c, mac)), None
    )
    if a_l_adresse is not None:
        return Correspondance(camera=_correspondante(a_l_adresse), deja_configuree=True)
    appareil = [camera for camera in toutes if mac and camera.mac == mac]
    if chemin is None or not appareil:
        return None
    meme_chemin = next((camera for camera in appareil if _chemin(camera.url_rtsp) == chemin), None)
    if meme_chemin is not None:
        return Correspondance(camera=_correspondante(meme_chemin), deja_configuree=True)
    return Correspondance(camera=_correspondante(appareil[0]), deja_configuree=False)


def _meme_appareil_possible(camera: Camera, mac: str | None) -> bool:
    """Faux seulement si les deux MAC sont connues et diffèrent : un autre Appareil répond à l'adresse."""
    return camera.mac is None or mac is None or camera.mac == mac


class AdresseMiseAJour(BaseModel):
    """Hôte de l'URL avant la Détection (IP ou nom) et nouvelle IP de l'Appareil."""

    ancienne: str
    nouvelle: str


class Rapprochement(BaseModel):
    """Caméra d'un Candidat ; `adresse_mise_a_jour` et `conflit` seulement pour un Appareil connu."""

    camera: CameraCorrespondante | None
    adresse_mise_a_jour: AdresseMiseAJour | None = None
    # Caméra qui occupe déjà la nouvelle URL : la Caméra de l'Appareil n'a pas été modifiée.
    conflit: CameraCorrespondante | None = None


def rapprocher(base: Session, candidats: Sequence[Candidat]) -> dict[Candidat, Rapprochement]:
    """Rapproche chaque Candidat des Caméras (actives ou désactivées) et suit les Appareils qui ont changé d'IP.

    D'abord par MAC : la plus ancienne Caméra de l'Appareil, au port du Candidat de préférence. Sinon par
    IP résolue et port, sauf une Caméra d'un autre Appareil. Une Caméra sans MAC à l'adresse d'un Candidat reçoit sa MAC.
    Un Appareil connu vu à une autre IP : l'hôte de l'URL de toutes ses Caméras devient cette IP (port, chemin,
    identifiants gardés), sauf si une Caméra qui ne bouge pas occupe déjà la nouvelle URL (conflit). Tout
    s'écrit en une transaction : deux Appareils peuvent échanger leurs IP.
    """
    # Lignes verrouillées : une sonde en cours n'écrit son état qu'après, et voit alors la nouvelle URL.
    toutes = list(base.scalars(select(Camera).order_by(Camera.id).with_for_update()))
    adresses = {camera.id: _adresses(camera.url_rtsp) for camera in toutes}
    for candidat in candidats:
        for camera in toutes:
            if candidat.mac and camera.mac is None and (candidat.ip, candidat.port) in adresses[camera.id]:
                camera.mac = candidat.mac
    ip_des_appareils: dict[str, IPv4Address] = {}
    for candidat in candidats:
        if candidat.mac:
            ip_des_appareils.setdefault(candidat.mac, candidat.ip)
    nouvelles_urls = {
        camera.id: _avec_hote(camera.url_rtsp, ip_des_appareils[camera.mac])
        for camera in toutes
        if camera.mac in ip_des_appareils and ip_des_appareils[camera.mac] not in {ip for ip, _ in adresses[camera.id]}
    }
    conflits = _retirer_conflits(toutes, nouvelles_urls)
    deplacees = [camera for camera in toutes if camera.id in nouvelles_urls]
    anciens_hotes = {camera.id: _decouper(camera.url_rtsp).hostname for camera in deplacees}
    _deplacer(base, deplacees, nouvelles_urls)
    for camera in deplacees:
        adresses[camera.id] = {(ip_des_appareils[camera.mac], _port(camera.url_rtsp))}
    # Avant le commit, qui expire les Caméras chargées.
    rapprochements = {c: _rapprochement(c, toutes, adresses, conflits, anciens_hotes) for c in candidats}
    base.commit()
    return rapprochements


def _rapprochement(
    candidat: Candidat,
    toutes: list[Camera],
    adresses: dict[int, set[tuple[IPv4Address, int]]],
    conflits: dict[int, Camera],
    anciens_hotes: dict[int, str],
) -> Rapprochement:
    appareil = [camera for camera in toutes if candidat.mac and camera.mac == candidat.mac]
    if not appareil:
        adresse = (candidat.ip, candidat.port)
        camera = next(
            (c for c in toutes if adresse in adresses[c.id] and _meme_appareil_possible(c, candidat.mac)), None
        )
        return Rapprochement(camera=None if camera is None else _correspondante(camera))
    # Tri stable par id : la plus ancienne au port du Candidat, sinon la plus ancienne de l'Appareil.
    appareil.sort(key=lambda camera: _port(camera.url_rtsp) != candidat.port)
    deplacee = next((camera for camera in appareil if camera.id in anciens_hotes), None)
    en_conflit = next((camera for camera in appareil if camera.id in conflits), None)
    return Rapprochement(
        camera=_correspondante(appareil[0]),
        adresse_mise_a_jour=None
        if deplacee is None
        else AdresseMiseAJour(ancienne=anciens_hotes[deplacee.id], nouvelle=str(candidat.ip)),
        conflit=None if en_conflit is None else _correspondante(conflits[en_conflit.id]),
    )


def _retirer_conflits(toutes: list[Camera], nouvelles_urls: dict[int, str]) -> dict[int, Camera]:
    """Retire de `nouvelles_urls` les Caméras dont la nouvelle URL est prise ; renvoie qui la prend.

    Une Caméra retirée garde son URL, qui peut à son tour bloquer une autre : jusqu'à ce que rien ne change.
    """
    conflits: dict[int, Camera] = {}
    while True:
        prises = {camera.url_rtsp: camera for camera in toutes if camera.id not in nouvelles_urls}
        bloquee = None
        for camera in toutes:
            url = nouvelles_urls.get(camera.id)
            if url is None:
                continue
            if url in prises:
                bloquee = camera
                conflits[camera.id] = prises[url]
                break
            prises[url] = camera
        if bloquee is None:
            return conflits
        del nouvelles_urls[bloquee.id]


def _deplacer(base: Session, deplacees: list[Camera], nouvelles_urls: dict[int, str]) -> None:
    """Deux passes : une URL provisoire unique d'abord, l'unicité des URL tient pendant un échange d'IP."""
    for camera in deplacees:
        camera.url_rtsp = f"{nouvelles_urls[camera.id]}#deplacement-{camera.id}"
    base.flush()
    for camera in deplacees:
        camera.url_rtsp = nouvelles_urls[camera.id]
        _remettre_a_unknown(camera)


def _avec_hote(url: str, ip: IPv4Address) -> str:
    morceaux = _decouper(url)
    acces, _, _ = morceaux.netloc.rpartition("@")
    port = f":{morceaux.port}" if morceaux.port is not None else ""
    return morceaux._replace(netloc=f"{acces}@{ip}{port}" if acces else f"{ip}{port}").geturl()


def _port(url: str) -> int:
    return _decouper(url).port or PORT_RTSP


def _chemin(url: str) -> str:
    morceaux = _decouper(url)
    requete = f"?{morceaux.query}" if morceaux.query else ""
    return "/" + morceaux.path.lstrip("/") + requete


def _adresses(url: str) -> set[tuple[IPv4Address, int]]:
    return {(ip, _port(url)) for ip in _resoudre(_decouper(url).hostname)}


def _correspondante(camera: Camera) -> CameraCorrespondante:
    return CameraCorrespondante(id=camera.id, nom=camera.nom)


def _resoudre(hote: str) -> set[IPv4Address]:
    try:
        return {IPv4Address(info[4][0]) for info in socket.getaddrinfo(hote, None, socket.AF_INET)}
    except OSError:
        return set()


def lire(base: Session, id_camera: int, racine_enregistrements: Path) -> CameraLue:
    return CameraLue.depuis(_trouver(base, id_camera), racine_enregistrements)


def creer(
    base: Session,
    nouvelle: NouvelleCamera,
    racine_enregistrements: Path,
    *,
    mac: str | None = None,
    codec: str | None = None,
) -> CameraLue:
    """`mac` et `codec` : lus sur le réseau pendant l'essai, jamais saisis par l'Administrateur."""
    camera = Camera(
        **nouvelle.model_dump(),
        active=True,
        enregistrement=False,
        etat="unknown",
        etat_verifie_le=None,
        mac=mac,
        codec=codec,
    )
    _enregistrer(base, camera)
    return CameraLue.depuis(camera, racine_enregistrements)


def modifier(
    base: Session,
    id_camera: int,
    modification: ModificationCamera,
    racine_enregistrements: Path,
    maintenant: Callable[[], datetime] | None = None,
) -> CameraLue:
    # Ligne verrouillée : une sonde en cours n'écrit son état qu'après, et voit alors la nouvelle URL.
    camera = _trouver(base, id_camera, verrouiller=True)
    champs = modification.model_dump(exclude_unset=True)
    sera_active = champs["active"] if "active" in champs else camera.active
    if champs.get("enregistrement") is True and not sera_active:
        raise EnregistrementRefuse
    url = champs.pop("url_rtsp", camera.url_rtsp)
    # L'URL masquée renvoyée telle quelle désigne l'URL stockée : le mot de passe est conservé.
    if url != masquer(camera.url_rtsp) and url != camera.url_rtsp:
        # Le contact ONVIF suit l'hôte : un autre mot de passe ou chemin le garde (et un changement d'IP par la MAC).
        if _decouper(url).hostname != _decouper(camera.url_rtsp).hostname:
            _oublier_onvif(camera)
        camera.url_rtsp = url
        _remettre_a_unknown(camera)
    for champ, valeur in champs.items():
        setattr(camera, champ, valeur)
    if not camera.active:
        camera.enregistrement = False
        _remettre_a_unknown(camera)
    enregistrement_allume = champs.get("enregistrement") is True and camera.enregistrement
    debit_encodage_manquant = camera.debit_encodage_kbit_s is None
    _enregistrer(base, camera)
    # Repli Débit d'écriture : peupler le débit d'encodage sans obliger un passage par les Réglages.
    if enregistrement_allume and debit_encodage_manquant and maintenant is not None:
        essayer_retenir_debit_encodage(base, id_camera, maintenant)
    return CameraLue.depuis(camera, racine_enregistrements)


class SecuriteOnvif(BaseModel):
    """Sécurité de l'échange ONVIF avec la caméra, montrée dans ses Réglages."""

    # Joint en HTTPS (docs/adr/0007-onvif-en-https-par-cle-memorisee.md).
    chiffre: bool
    # Empreinte SHA-256 (hexadécimal) de la clé publique du Certificat de l'Appareil, et sa date de mémorisation ;
    # `None` hors HTTPS.
    empreinte: str | None
    empreinte_memorisee_le: datetime | None
    # TLS 1.0 ou 1.1 négocié : accepté, mais signalé.
    tls_ancien: bool
    # ONVIF en clair avec un mot de passe de moins de `LONGUEUR_MOT_DE_PASSE_SUR` caractères : son empreinte
    # WS-Security (SHA-1) circule en clair et se casse hors ligne. Jamais le mot de passe ni sa longueur.
    mot_de_passe_court: bool


class ReglagesLus(onvif.Reglages):
    securite: SecuriteOnvif


class CertificatsCompares(BaseModel):
    """Clé mémorisée (et sa date) et clé que la caméra présente, pour que l'Administrateur tranche."""

    # `None` : changée dès le premier contact, au milieu de l'échange.
    empreinte_memorisee: str | None
    empreinte_memorisee_le: datetime | None
    empreinte_presentee: str | None


class CertificatChange(onvif.ErreurOnvif):
    """`certificat_change` d'une Caméra, avec les deux empreintes."""

    def __init__(self, certificats: CertificatsCompares) -> None:
        super().__init__("certificat_change", empreinte_vue=certificats.empreinte_presentee)
        self.certificats = certificats


class ConfianceCertificat(BaseModel):
    # Empreinte que les Réglages ont montrée comme présentée : la caméra doit la présenter encore.
    empreinte: str = Field(pattern=r"^[0-9a-f]{64}$")


def lire_reglages(base: Session, id_camera: int, maintenant: Callable[[], datetime]) -> ReglagesLus:
    """Réglages lus sur la caméra d'une Caméra active, par ONVIF, et sécurité de l'échange ; retient le contact.

    Lève `CameraIntrouvable` (inconnue ou désactivée) ou `onvif.ErreurOnvif`.
    """
    reglages, securite = _par_onvif(
        base, id_camera, maintenant, lambda url, retenu, codec: onvif.lire_reglages(url, retenu, maintenant, codec)
    )
    _retenir_debit_encodage(base, id_camera, reglages.encodage)
    return ReglagesLus(**reglages.model_dump(), securite=securite)


def modifier_reglages(
    base: Session, id_camera: int, modification: onvif.ModificationReglages, maintenant: Callable[[], datetime]
) -> onvif.ResultatModification:
    """Envoie la modification à la caméra d'une Caméra active, par ONVIF, puis la relit ; retient le contact.

    Lève `CameraIntrouvable` (inconnue ou désactivée) ou `onvif.ErreurOnvif`.
    """
    resultat, _ = _par_onvif(
        base,
        id_camera,
        maintenant,
        lambda url, retenu, codec: onvif.modifier_reglages(url, retenu, modification, maintenant, codec),
    )
    _retenir_debit_encodage(base, id_camera, resultat.reglages.encodage)
    return resultat


def _retenir_debit_encodage(base: Session, id_camera: int, encodage: onvif.Encodage) -> None:
    """Mémorise le débit max d'Encodage pour le repli du Débit d'écriture (ADR 0012)."""
    valeurs = encodage.valeurs
    if valeurs is None or valeurs.debit_max is None:
        return
    base.execute(update(Camera).where(Camera.id == id_camera).values(debit_encodage_kbit_s=valeurs.debit_max))
    base.commit()


def essayer_retenir_debit_encodage(base: Session, id_camera: int, maintenant: Callable[[], datetime]) -> None:
    """Best-effort : lit l'Encodage ONVIF pour le repli Débit d'écriture. Échec silencieux (caméra muette, etc.)."""
    try:
        reglages, _ = _par_onvif(
            base, id_camera, maintenant, lambda url, retenu, codec: onvif.lire_reglages(url, retenu, maintenant, codec)
        )
    except (CameraIntrouvable, CertificatChange, onvif.ErreurOnvif):
        return
    _retenir_debit_encodage(base, id_camera, reglages.encodage)


def mettre_a_l_heure(base: Session, id_camera: int, maintenant: Callable[[], datetime]) -> onvif.Horloge:
    """Met la caméra d'une Caméra active à l'heure du Site, par ONVIF, puis relit son Horloge ; retient le contact.

    Lève `CameraIntrouvable` (inconnue ou désactivée) ou `onvif.ErreurOnvif`.
    """
    horloge, _ = _par_onvif(
        base, id_camera, maintenant, lambda url, retenu, _codec: onvif.mettre_a_l_heure(url, retenu, maintenant)
    )
    return horloge


def caler(
    base: Session, id_camera: int, maintenant: Callable[[], datetime], serveur_ntp: str, fuseau_posix: str
) -> onvif.Horloge:
    """Cale la caméra d'une Caméra active sur le Serveur de temps du Site, par ONVIF, puis relit son Horloge ; retient
    le contact (et la clé au premier contact HTTPS).

    Lève `CameraIntrouvable` (inconnue ou désactivée) ou `onvif.ErreurOnvif`.
    """
    horloge, _ = _par_onvif(
        base,
        id_camera,
        maintenant,
        lambda url, retenu, _codec: onvif.caler(url, retenu, serveur_ntp, fuseau_posix, maintenant),
    )
    return horloge


def ids_actives(base: Session) -> list[int]:
    return list(base.scalars(select(Camera.id).where(Camera.active).order_by(Camera.id)))


def _par_onvif[T](
    base: Session,
    id_camera: int,
    maintenant: Callable[[], datetime],
    echange: Callable[[str, onvif.Retenu, str | None], tuple[T, onvif.Contact]],
) -> tuple[T, SecuriteOnvif]:
    """Échange ONVIF avec la caméra d'une Caméra active (URL RTSP, contact retenu, codec connu du Flux) ; retient le
    contact, et la clé au premier contact HTTPS."""
    camera = _trouver_active(base, id_camera)
    url = camera.url_rtsp
    retenu = onvif.Retenu(
        camera.schema_onvif, camera.port_onvif, camera.empreinte_onvif, camera.onvif_en_clair_accepte
    )
    memorisee_le = camera.empreinte_onvif_le
    codec = camera.codec
    # Pas de transaction ouverte pendant l'échange réseau.
    base.rollback()
    try:
        resultat, contact = echange(url, retenu, codec)
    except onvif.ErreurOnvif as erreur:
        _journaliser_refus(id_camera, retenu, erreur)
        if erreur.code == "certificat_change":
            raise CertificatChange(
                CertificatsCompares(
                    empreinte_memorisee=retenu.empreinte,
                    empreinte_memorisee_le=memorisee_le,
                    empreinte_presentee=erreur.empreinte_vue,
                )
            ) from erreur
        raise
    valeurs: dict[str, object] = {}
    if (contact.schema, contact.port) != (retenu.schema, retenu.port):
        valeurs |= {"schema_onvif": contact.schema, "port_onvif": contact.port}
    if contact.empreinte is not None and retenu.empreinte is None:
        memorisee_le = maintenant()
        valeurs |= {"empreinte_onvif": contact.empreinte, "empreinte_onvif_le": memorisee_le}
    if valeurs:
        # Seulement si l'URL n'a pas changé entre-temps : le contact est celui de cet hôte.
        base.execute(update(Camera).where(Camera.id == id_camera, Camera.url_rtsp == url).values(**valeurs))
        base.commit()
    chiffre = contact.schema == "https"
    securite = SecuriteOnvif(
        chiffre=chiffre,
        empreinte=contact.empreinte if chiffre else None,
        empreinte_memorisee_le=memorisee_le if chiffre else None,
        tls_ancien=contact.tls_ancien,
        mot_de_passe_court=not chiffre and _mot_de_passe_court(url),
    )
    return resultat, securite


def _mot_de_passe_court(url: str) -> bool:
    """Mot de passe de l'URL RTSP, décodé, de 1 à `LONGUEUR_MOT_DE_PASSE_SUR` - 1 caractères ; absent : non."""
    mot_de_passe = unquote(urlsplit(url).password or "")
    return 0 < len(mot_de_passe) < LONGUEUR_MOT_DE_PASSE_SUR


def _journaliser_refus(id_camera: int, retenu: onvif.Retenu, erreur: onvif.ErreurOnvif) -> None:
    """Journalise un refus de sécurité (certificat changé, HTTPS indisponible), avec les empreintes."""
    if erreur.code == "certificat_change":
        journal.warning(
            "ONVIF : Caméra %s, certificat changé (mémorisé %s, présenté %s) : refusé",
            id_camera,
            retenu.empreinte,
            erreur.empreinte_vue,
        )
    elif erreur.code == "https_indisponible":
        journal.warning(
            "ONVIF : Caméra %s, HTTPS indisponible (certificat mémorisé %s) : refusé, sans repli HTTP",
            id_camera,
            retenu.empreinte,
        )


def faire_confiance(base: Session, id_camera: int, empreinte: str, maintenant: Callable[[], datetime]) -> None:
    """Mémorise la clé que la caméra d'une Caméra active présente, si c'est bien `empreinte` (celle montrée à
    l'Administrateur) ; le contact devient HTTPS.

    Lève `CameraIntrouvable`, `CertificatNonPresente` ou `onvif.ErreurOnvif` (la caméra ne répond pas en HTTPS).
    """
    camera = _trouver_active(base, id_camera)
    url, ancienne = camera.url_rtsp, camera.empreinte_onvif
    base.rollback()
    presentee = onvif.empreinte_presentee(url)
    if presentee != empreinte:
        journal.warning(
            "ONVIF : Caméra %s, confiance refusée : %s n'est pas le certificat présenté (%s)",
            id_camera,
            empreinte,
            presentee,
        )
        raise CertificatNonPresente
    base.execute(
        update(Camera)
        .where(Camera.id == id_camera, Camera.url_rtsp == url)
        .values(
            schema_onvif="https",
            port_onvif=onvif.PORT_HTTPS,
            empreinte_onvif=presentee,
            empreinte_onvif_le=maintenant(),
        )
    )
    base.commit()
    journal.info("ONVIF : Caméra %s, confiance au nouveau certificat %s (remplace %s)", id_camera, presentee, ancienne)


def oublier_certificat(base: Session, id_camera: int) -> None:
    """Efface clé, schéma et port ONVIF retenus : le contact suivant repart de zéro.

    Lève `CameraIntrouvable` (inconnue ou désactivée).
    """
    camera = _trouver_active(base, id_camera)
    ancienne = camera.empreinte_onvif
    _oublier_onvif(camera)
    base.commit()
    journal.info("ONVIF : Caméra %s, certificat %s oublié", id_camera, ancienne)


def accepter_en_clair(base: Session, id_camera: int, accepte: bool) -> None:
    """« Régler quand même en clair » (`accepte`), ou retrait de l'accord. Lève `CameraIntrouvable` (inconnue ou
    désactivée).

    Une Caméra en HTTPS n'est jamais réglée en clair : l'accord ne sert qu'à une caméra sans HTTPS.
    """
    camera = _trouver_active(base, id_camera)
    camera.onvif_en_clair_accepte = accepte
    base.commit()
    journal.info("ONVIF : Caméra %s, ONVIF en clair %s", id_camera, "accepté" if accepte else "retiré")


def _oublier_onvif(camera: Camera) -> None:
    """Contact, clé et accord ONVIF retenus pour l'hôte de l'URL : à chercher, et à demander, de nouveau.

    Gardés tant que l'hôte reste celui de l'Appareil : autre mot de passe ou chemin, nouvelle IP suivie par la MAC.
    """
    camera.port_onvif = None
    camera.schema_onvif = None
    camera.empreinte_onvif = None
    camera.empreinte_onvif_le = None
    camera.onvif_en_clair_accepte = False


def supprimer(base: Session, id_camera: int, racine_enregistrements: Path) -> None:
    camera = _trouver(base, id_camera)
    if camera.active:
        raise CameraActive
    dossier = racine_enregistrements / chemin_flux(camera.id)
    base.delete(camera)
    base.commit()
    try:
        shutil.rmtree(dossier)
    except FileNotFoundError:
        pass
    except NotADirectoryError:
        dossier.unlink(missing_ok=True)


def _trouver(base: Session, id_camera: int, verrouiller: bool = False) -> Camera:
    camera = base.get(Camera, id_camera, with_for_update=verrouiller)
    if camera is None:
        raise CameraIntrouvable
    return camera


def _trouver_active(base: Session, id_camera: int) -> Camera:
    """Caméra active : seules elles ont des Réglages. Inconnue ou désactivée → `CameraIntrouvable`."""
    camera = _trouver(base, id_camera)
    if not camera.active:
        raise CameraIntrouvable
    return camera


def _remettre_a_unknown(camera: Camera) -> None:
    camera.etat = "unknown"
    camera.etat_verifie_le = None
    camera.raison_etat = None


def _enregistrer(base: Session, camera: Camera) -> None:
    requete = select(Camera.id).where(or_(Camera.nom == camera.nom, Camera.url_rtsp == camera.url_rtsp))
    if camera.id is not None:
        requete = requete.where(Camera.id != camera.id)
    # Sans autoflush : la Caméra modifiée n'est pas écrite avant la vérification.
    with base.no_autoflush:
        pris = base.scalar(requete) is not None
    if pris:
        base.rollback()
        raise Doublon
    base.add(camera)
    try:
        base.commit()
    except IntegrityError:
        # Deux écritures simultanées passent la vérification : la contrainte d'unicité tranche.
        base.rollback()
        raise Doublon from None
