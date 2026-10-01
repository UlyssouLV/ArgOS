"""Caméras du Site : URL RTSP (validation, masquage, hôte et port) et règles de gestion."""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import SplitResult, urlsplit

from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from argos_api.modeles import Camera

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
        )


def lister(base: Session) -> list[CameraLue]:
    return [CameraLue.depuis(c) for c in base.scalars(select(Camera).order_by(Camera.id))]


def lire(base: Session, id_camera: int) -> CameraLue:
    return CameraLue.depuis(_trouver(base, id_camera))


def creer(base: Session, nouvelle: NouvelleCamera) -> CameraLue:
    camera = Camera(**nouvelle.model_dump(), active=True, etat="unknown", etat_verifie_le=None)
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
