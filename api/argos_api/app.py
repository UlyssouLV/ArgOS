"""API du Site : connexion de l'Administrateur, gestion des Caméras et surveillance de leur état."""

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from argos_api import cameras, sessions, sonde
from argos_api.cameras import CameraLue, ModificationCamera, NouvelleCamera
from argos_api.configuration import Configuration, charger
from argos_api.frein import FreinForceBrute, TropDEchecs
from argos_api.surveillance import Surveillance

COOKIE_SESSION = "argos_session"

Horloge = Callable[[], datetime]


def horloge_systeme() -> datetime:
    return datetime.now(UTC)


class Identifiants(BaseModel):
    identifiant: str
    mot_de_passe: str


class Moi(BaseModel):
    identifiant: str


def creer_app(
    configuration: Configuration | None = None, horloge: Horloge = horloge_systeme
) -> FastAPI:
    """Horloge et configuration injectables : les règles de temps et de mot de passe se testent sans attendre."""
    configuration = configuration or charger()
    frein = FreinForceBrute(horloge)
    ouvrir_base = sessionmaker(create_engine(configuration.url_base))

    @asynccontextmanager
    async def cycle_de_vie(_: FastAPI) -> AsyncIterator[None]:
        surveillance = Surveillance(
            ouvrir_base, sonde.sonder, configuration.intervalle_sonde, configuration.delai_sonde, horloge
        )
        surveillance.demarrer()
        yield
        surveillance.arreter()

    app = FastAPI(
        lifespan=cycle_de_vie,
        title="ArgOS — API du Site",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
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

    app.include_router(_routes_cameras(base, administrateur_connecte))
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
