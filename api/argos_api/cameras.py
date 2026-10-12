"""Caméras du Site : URL RTSP (validation, masquage, hôte et port) et règles de gestion."""

import socket
from collections.abc import Sequence
from datetime import datetime
from ipaddress import IPv4Address
from typing import Annotated, Literal
from urllib.parse import SplitResult, urlsplit

from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from argos_api.detection import Candidat
from argos_api.modeles import Camera
from argos_api.pont import chemin_flux

PORT_RTSP = 554
MASQUE = "***"

Etat = Literal["unknown", "online", "offline"]


class CameraIntrouvable(Exception):
    pass


class Doublon(Exception):
    """Le nom ou l'URL est déjà pris, y compris par une Caméra désactivée."""


class CameraActive(Exception):
    """Seule une Caméra désactivée peut être supprimée."""


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
    raison_etat: str | None
    # Chemin MediaMTX qui relaie le Flux (docs/adr/0001-mediamtx-en-pont.md) ; aucun si désactivée.
    chemin_flux: str | None
    # MAC de l'Appareil, `aa:bb:cc:dd:ee:ff` ; `None` : inconnue. Jamais modifiable par l'Administrateur.
    mac: str | None

    @classmethod
    def depuis(cls, camera: Camera) -> "CameraLue":
        morceaux = _decouper(camera.url_rtsp)
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
        )


def lister(base: Session) -> list[CameraLue]:
    return [CameraLue.depuis(c) for c in base.scalars(select(Camera).order_by(Camera.id))]


def urls_actives(base: Session) -> dict[int, str]:
    """URL RTSP stockée (mot de passe compris) de chaque Caméra active, par id."""
    lignes = base.execute(select(Camera.id, Camera.url_rtsp).where(Camera.active))
    return {id_camera: url for id_camera, url in lignes}


class CameraCorrespondante(BaseModel):
    id: int
    nom: str


def par_adresse(base: Session) -> dict[tuple[IPv4Address, int], CameraCorrespondante]:
    """Caméras (actives ou désactivées) par IP résolue de l'hôte de leur URL et port.

    Plusieurs Caméras à la même adresse (chemins différents) : la plus ancienne. Hôte introuvable : ignoré.
    """
    adresses: dict[tuple[IPv4Address, int], CameraCorrespondante] = {}
    for camera in base.scalars(select(Camera).order_by(Camera.id)):
        for adresse in _adresses(camera.url_rtsp):
            adresses.setdefault(adresse, _correspondante(camera))
    return adresses


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
    IP résolue et port, comme `par_adresse`. Une Caméra sans MAC à l'adresse d'un Candidat reçoit sa MAC.
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
        camera = next((camera for camera in toutes if adresse in adresses[camera.id]), None)
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


def _adresses(url: str) -> set[tuple[IPv4Address, int]]:
    return {(ip, _port(url)) for ip in _resoudre(_decouper(url).hostname)}


def _correspondante(camera: Camera) -> CameraCorrespondante:
    return CameraCorrespondante(id=camera.id, nom=camera.nom)


def _resoudre(hote: str) -> set[IPv4Address]:
    try:
        return {IPv4Address(info[4][0]) for info in socket.getaddrinfo(hote, None, socket.AF_INET)}
    except OSError:
        return set()


def lire(base: Session, id_camera: int) -> CameraLue:
    return CameraLue.depuis(_trouver(base, id_camera))


def creer(base: Session, nouvelle: NouvelleCamera, mac: str | None = None) -> CameraLue:
    """`mac` : lue sur le réseau pendant l'essai, jamais saisie par l'Administrateur."""
    camera = Camera(**nouvelle.model_dump(), active=True, etat="unknown", etat_verifie_le=None, mac=mac)
    _enregistrer(base, camera)
    return CameraLue.depuis(camera)


def modifier(base: Session, id_camera: int, modification: ModificationCamera) -> CameraLue:
    # Ligne verrouillée : une sonde en cours n'écrit son état qu'après, et voit alors la nouvelle URL.
    camera = _trouver(base, id_camera, verrouiller=True)
    champs = modification.model_dump(exclude_unset=True)
    url = champs.pop("url_rtsp", camera.url_rtsp)
    # L'URL masquée renvoyée telle quelle désigne l'URL stockée : le mot de passe est conservé.
    if url != masquer(camera.url_rtsp) and url != camera.url_rtsp:
        camera.url_rtsp = url
        _remettre_a_unknown(camera)
    for champ, valeur in champs.items():
        setattr(camera, champ, valeur)
    if not camera.active:
        _remettre_a_unknown(camera)
    _enregistrer(base, camera)
    return CameraLue.depuis(camera)


def supprimer(base: Session, id_camera: int) -> None:
    camera = _trouver(base, id_camera)
    if camera.active:
        raise CameraActive
    base.delete(camera)
    base.commit()


def _trouver(base: Session, id_camera: int, verrouiller: bool = False) -> Camera:
    camera = base.get(Camera, id_camera, with_for_update=verrouiller)
    if camera is None:
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
