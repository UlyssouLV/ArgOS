"""API du Site : connexion de l'Administrateur."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from argos_api import sessions
from argos_api.configuration import Configuration

COOKIE_SESSION = "argos_session"


class Identifiants(BaseModel):
    identifiant: str
    mot_de_passe: str


class Moi(BaseModel):
    identifiant: str


def creer_app(configuration: Configuration | None = None) -> FastAPI:
    configuration = configuration or Configuration()
    ouvrir_base = sessionmaker(create_engine(configuration.url_base))

    app = FastAPI(
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
        if jeton is None or not sessions.est_valide(base, jeton):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non connecté.")
        return configuration.identifiant

    @app.post("/api/session", status_code=status.HTTP_204_NO_CONTENT)
    def se_connecter(identifiants: Identifiants, base: Base) -> Response:
        if not sessions.identifiants_valides(
            configuration, identifiants.identifiant, identifiants.mot_de_passe
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiant ou mot de passe incorrect.")
        reponse = Response(status_code=status.HTTP_204_NO_CONTENT)
        reponse.set_cookie(COOKIE_SESSION, sessions.ouvrir(base), httponly=True, samesite="lax")
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

    return app
