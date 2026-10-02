"""API du Site : connexion de l'Administrateur, gestion et Détection des Caméras, surveillance de leur état et pont MediaMTX."""

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from time import monotonic
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from argos_api import cameras, detection, sessions, soi, sonde
from argos_api.boucle import BoucleDeFond
from argos_api.cameras import CameraLue, ModificationCamera, NouvelleCamera
from argos_api.configuration import Configuration, ReglageDetection, charger
from argos_api.frein import FreinForceBrute, TropDEchecs
from argos_api.pont import Pont
from argos_api.surveillance import Surveillance

COOKIE_SESSION = "argos_session"
# Réconciliation des Caméras actives avec les chemins MediaMTX, en secondes (docs/adr/0001-mediamtx-en-pont.md).
INTERVALLE_PONT_S = 10
# Délai de chaque sonde de la Détection (connexion puis réponse RTSP), en secondes.
DELAI_DETECTION_S = 1.5

Horloge = Callable[[], datetime]


def horloge_systeme() -> datetime:
    return datetime.now(UTC)


class Identifiants(BaseModel):
    identifiant: str
    mot_de_passe: str


class Moi(BaseModel):
    identifiant: str


class Instance(BaseModel):
    instance: str


class EtatDetection(BaseModel):
    configuree: bool
    sous_reseaux: list[str]
    ports: list[int]
    raison: str | None


class CandidatLu(BaseModel):
    ip: str
    port: int


class ResultatDetection(BaseModel):
    sous_reseaux: list[str]
    ports: list[int]
    duree_s: float
    candidats: list[CandidatLu]


def creer_app(
    configuration: Configuration | None = None, horloge: Horloge = horloge_systeme
) -> FastAPI:
    """Horloge et configuration injectables : les règles de temps et de mot de passe se testent sans attendre."""
    configuration = configuration or charger()
    frein = FreinForceBrute(horloge)
    ouvrir_base = sessionmaker(create_engine(configuration.url_base))

    @asynccontextmanager
    async def cycle_de_vie(_: FastAPI) -> AsyncIterator[None]:
        surveillance = Surveillance(ouvrir_base, sonde.sonder, configuration.delai_sonde, horloge)
        pont = Pont(configuration.url_api_mediamtx, configuration.delai_mediamtx)

        def reconcilier() -> None:
            with ouvrir_base() as base:
                actives = cameras.urls_actives(base)
            pont.reconcilier(actives)

        boucles = [
            BoucleDeFond("surveillance-cameras", surveillance.sonder_tout, configuration.intervalle_sonde),
            BoucleDeFond("pont-mediamtx", reconcilier, INTERVALLE_PONT_S),
        ]
        for boucle in boucles:
            boucle.demarrer()
        yield
        for boucle in boucles:
            boucle.arreter()

    app = FastAPI(
        lifespan=cycle_de_vie,
        title="ArgOS — API du Site",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    # L'UI est servie sur une autre origine (port 8080, ou 5173 en dev) : CORS avec credentials,
    # jamais `*`, seulement les origines exactes de la configuration (docs/securite.md).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.liste_origines_autorisees(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    def base() -> Iterator[Session]:
        with ouvrir_base() as s:
            yield s

    Base = Annotated[Session, Depends(base)]
    JetonSession = Annotated[str | None, Cookie(alias=COOKIE_SESSION)]

    def administrateur_connecte(base: Base, jeton: JetonSession = None) -> str:
        if jeton is None or not sessions.est_valide(
            base, jeton, configuration.mot_de_passe, horloge()
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non connecté.")
        return configuration.identifiant

    @app.post("/api/session", status_code=status.HTTP_204_NO_CONTENT)
    def se_connecter(identifiants: Identifiants, base: Base) -> Response:
        try:
            valides = frein.essayer(
                lambda: sessions.identifiants_valides(
                    configuration, identifiants.identifiant, identifiants.mot_de_passe
                )
            )
        except TropDEchecs:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Trop d'échecs de connexion, réessayer plus tard."
            ) from None
        if not valides:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiant ou mot de passe incorrect.")
        reponse = Response(status_code=status.HTTP_204_NO_CONTENT)
        jeton = sessions.ouvrir(base, configuration.mot_de_passe, horloge())
        reponse.set_cookie(COOKIE_SESSION, jeton, httponly=True, samesite="lax")
        return reponse

    @app.delete("/api/session", status_code=status.HTTP_204_NO_CONTENT)
    def se_deconnecter(base: Base, jeton: JetonSession = None) -> Response:
        if jeton is not None:
            sessions.fermer(base, jeton)
        reponse = Response(status_code=status.HTTP_204_NO_CONTENT)
        reponse.delete_cookie(COOKIE_SESSION, httponly=True, samesite="lax")
        return reponse

    @app.get("/api/moi")
    def moi(identifiant: Annotated[str, Depends(administrateur_connecte)]) -> Moi:
        return Moi(identifiant=identifiant)

    @app.get(soi.CHEMIN_INSTANCE)
    def instance() -> Instance:
        """Identité de cette instance, sans session : la Détection s'y reconnaît (argos_api/soi.py)."""
        return Instance(instance=soi.JETON_INSTANCE)

    app.include_router(_routes_cameras(base, administrateur_connecte))
    hote_pont = urlsplit(configuration.url_api_mediamtx).hostname or ""
    app.include_router(_routes_detection(configuration.reglage_detection(), hote_pont, administrateur_connecte))
    return app


def _routes_cameras(base: Callable[[], Iterator[Session]], administrateur_connecte: Callable) -> APIRouter:
    """Toutes les routes des Caméras exigent une session valide : rien ne fuite sans connexion."""
    Base = Annotated[Session, Depends(base)]
    routes = APIRouter(prefix="/api/cameras", dependencies=[Depends(administrateur_connecte)])

    @routes.get("")
    def lister(base: Base) -> list[CameraLue]:
        return cameras.lister(base)

    @routes.post("", status_code=status.HTTP_201_CREATED)
    def creer(nouvelle: NouvelleCamera, base: Base) -> CameraLue:
        with _erreurs_cameras():
            return cameras.creer(base, nouvelle)

    @routes.get("/{id_camera}")
    def lire(id_camera: int, base: Base) -> CameraLue:
        with _erreurs_cameras():
            return cameras.lire(base, id_camera)

    @routes.patch("/{id_camera}")
    def modifier(id_camera: int, modification: ModificationCamera, base: Base) -> CameraLue:
        with _erreurs_cameras():
            return cameras.modifier(base, id_camera, modification)

    @routes.delete("/{id_camera}", status_code=status.HTTP_204_NO_CONTENT)
    def supprimer(id_camera: int, base: Base) -> None:
        with _erreurs_cameras():
            cameras.supprimer(base, id_camera)

    return routes


def _routes_detection(reglage: ReglageDetection, hote_pont: str, administrateur_connecte: Callable) -> APIRouter:
    """Détection réservée à une session valide : un inconnu du réseau ne fait pas balayer le réseau par ArgOS."""
    routes = APIRouter(prefix="/api/detection", dependencies=[Depends(administrateur_connecte)])
    sous_reseaux = [str(reseau) for reseau in reglage.sous_reseaux]

    @routes.get("")
    def decrire() -> EtatDetection:
        return EtatDetection(
            configuree=reglage.raison is None, sous_reseaux=sous_reseaux, ports=reglage.ports, raison=reglage.raison
        )

    @routes.post("")
    def detecter() -> ResultatDetection:
        if reglage.raison is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, reglage.raison)
        debut = monotonic()
        exclues = soi.adresses_des_conteneurs([hote_pont])
        trouves = detection.detecter(reglage.sous_reseaux, reglage.ports, exclues, DELAI_DETECTION_S)
        argos = soi.publient_cette_api({c.ip for c in trouves}, DELAI_DETECTION_S)
        return ResultatDetection(
            sous_reseaux=sous_reseaux,
            ports=reglage.ports,
            duree_s=round(monotonic() - debut, 1),
            candidats=[CandidatLu(ip=str(c.ip), port=c.port) for c in trouves if c.ip not in argos],
        )

    return routes


@contextmanager
def _erreurs_cameras() -> Iterator[None]:
    try:
        yield
    except cameras.CameraIntrouvable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caméra introuvable.") from None
    except cameras.Doublon:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Une Caméra porte déjà ce nom ou cette URL (désactivée comprise)."
        ) from None
    except cameras.CameraActive:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Désactiver la Caméra avant de la supprimer."
        ) from None
