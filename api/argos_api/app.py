"""API du Site : connexion de l'Administrateur, gestion et Détection des Caméras, surveillance de leur état et pont MediaMTX."""

import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from time import monotonic
from ipaddress import IPv4Address, IPv4Network
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from argos_api import cameras, detection, essai, sessions, soi, sonde
from argos_api.apercu import Apercus, AucunApercu, EssaiAnnule
from argos_api.boucle import BoucleDeFond
from argos_api.cameras import CameraCorrespondante, CameraLue, ModificationCamera, NouvelleCamera
from argos_api.configuration import Configuration, ReglageDetection, charger
from argos_api.frein import FreinForceBrute, TropDEchecs
from argos_api.pont import Pont
from argos_api.surveillance import Surveillance

COOKIE_SESSION = "argos_session"
# Réconciliation des Caméras actives avec les chemins MediaMTX, en secondes (docs/adr/0001-mediamtx-en-pont.md).
INTERVALLE_PONT_S = 10
# Délai de chaque sonde de la Détection (connexion puis réponse RTSP), en secondes.
DELAI_DETECTION_S = 1.5
DETECTION_EN_COURS = "Une Détection est déjà en cours : attendre son résultat avant d'en relancer une."
# Retrait des Aperçus expirés, en secondes.
INTERVALLE_APERCU_S = 1
# Réseau local : seules ces adresses (RFC 1918) peuvent être essayées.
RESEAUX_LOCAUX = [IPv4Network(r) for r in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
HORS_RESEAU_LOCAL = "Adresse hors du réseau local (10.x, 172.16-31.x, 192.168.x) : ArgOS n'essaie que les caméras du Site."
ADRESSE_D_ARGOS = "Cette adresse est celle d'ArgOS, pas d'une caméra."
ESSAI_EN_COURS = "Un essai est déjà en cours : attendre son résultat avant d'en lancer un autre."

journal = logging.getLogger("argos_api.detection")
journal_essai = logging.getLogger("argos_api.essai")

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
    # Diagnostic, non affiché par l'UI : statut de la réponse à OPTIONS et en-tête `Server`.
    statut_rtsp: int
    serveur: str | None
    # Caméra du Site (active ou désactivée) à la même IP résolue et au même port ; `None` : nouveau.
    camera: CameraCorrespondante | None


class ResultatDetection(BaseModel):
    sous_reseaux: list[str]
    ports: list[int]
    duree_s: float
    candidats: list[CandidatLu]


class DemandeEssai(BaseModel):
    ip: IPv4Address
    port: int = Field(cameras.PORT_RTSP, gt=0, lt=65536)
    # Portés par l'URL de l'essai, puis de la Caméra ajoutée ; jamais renvoyés au navigateur.
    identifiant: str | None = None
    mot_de_passe: str | None = Field(None, repr=False)
    # Saisi quand aucun chemin courant ne répond (`flux_introuvable`) : seul ce chemin est essayé.
    chemin: str | None = None


class EssaiLu(BaseModel):
    issue: essai.Issue
    chemin: str | None
    codec: str | None
    # Chemin MediaMTX de l'Aperçu, à lire en WebRTC ; seulement si `flux_trouve`.
    apercu: str | None
    # Sans `POST /api/essai/renouveler` pendant ce délai, l'Aperçu est retiré.
    expiration_s: float


class AjoutDepuisEssai(BaseModel):
    nom: str = Field(min_length=1)
    emplacement: str | None = None


def creer_app(
    configuration: Configuration | None = None, horloge: Horloge = horloge_systeme
) -> FastAPI:
    """Horloge et configuration injectables : les règles de temps et de mot de passe se testent sans attendre."""
    configuration = configuration or charger()
    _journaux_sur_la_sortie()
    frein = FreinForceBrute(horloge)
    ouvrir_base = sessionmaker(create_engine(configuration.url_base))
    pont = Pont(configuration.url_api_mediamtx, configuration.delai_mediamtx)
    apercus = Apercus(pont, configuration.expiration_apercu)

    @asynccontextmanager
    async def cycle_de_vie(_: FastAPI) -> AsyncIterator[None]:
        surveillance = Surveillance(ouvrir_base, sonde.sonder, configuration.delai_sonde, horloge)

        def reconcilier() -> None:
            with ouvrir_base() as base:
                actives = cameras.urls_actives(base)
            pont.reconcilier(actives)

        boucles = [
            BoucleDeFond("surveillance-cameras", surveillance.sonder_tout, configuration.intervalle_sonde),
            BoucleDeFond("pont-mediamtx", reconcilier, INTERVALLE_PONT_S),
            BoucleDeFond("apercus", apercus.entretenir, INTERVALLE_APERCU_S),
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
    app.include_router(
        _routes_detection(configuration.reglage_detection(), hote_pont, base, administrateur_connecte)
    )
    app.include_router(
        _routes_essai(apercus, configuration, hote_pont, base, administrateur_connecte)
    )
    return app


def _journaux_sur_la_sortie() -> None:
    """uvicorn ne journalise que ses propres messages : ceux d'ArgOS (dès INFO) vont aussi sur la sortie."""
    racine = logging.getLogger("argos_api")
    if not racine.handlers:
        sortie = logging.StreamHandler()
        sortie.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        racine.addHandler(sortie)
        racine.setLevel(logging.INFO)


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


def _routes_detection(
    reglage: ReglageDetection,
    hote_pont: str,
    base: Callable[[], Iterator[Session]],
    administrateur_connecte: Callable,
) -> APIRouter:
    """Détection réservée à une session valide : un inconnu du réseau ne fait pas balayer le réseau par ArgOS.

    Une seule à la fois : deux Détections simultanées doubleraient le trafic envoyé au réseau du Site.
    """
    Base = Annotated[Session, Depends(base)]
    routes = APIRouter(prefix="/api/detection", dependencies=[Depends(administrateur_connecte)])
    sous_reseaux = [str(reseau) for reseau in reglage.sous_reseaux]
    une_seule = threading.Lock()

    @routes.get("")
    def decrire() -> EtatDetection:
        return EtatDetection(
            configuree=reglage.raison is None, sous_reseaux=sous_reseaux, ports=reglage.ports, raison=reglage.raison
        )

    @routes.post("")
    def detecter(base: Base) -> ResultatDetection:
        if reglage.raison is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, reglage.raison)
        if not une_seule.acquire(blocking=False):
            raise HTTPException(status.HTTP_409_CONFLICT, DETECTION_EN_COURS)
        try:
            debut = monotonic()
            exclues = soi.adresses_des_conteneurs([hote_pont])
            trouves = detection.detecter(reglage.sous_reseaux, reglage.ports, exclues, DELAI_DETECTION_S)
            argos = soi.publient_cette_api({c.ip for c in trouves}, DELAI_DETECTION_S)
            candidats = [c for c in trouves if c.ip not in argos]
            duree_s = round(monotonic() - debut, 1)
        finally:
            une_seule.release()
        connues = cameras.par_adresse(base)
        for c in candidats:
            journal.info("Détection : Candidat %s:%s RTSP %s Server %s", c.ip, c.port, c.statut_rtsp, c.serveur)
        journal.info(
            "Détection : bilan sous-réseaux %s, ports %s, %s s, %s Candidat(s)",
            ",".join(sous_reseaux), ",".join(map(str, reglage.ports)), duree_s, len(candidats),
        )
        return ResultatDetection(
            sous_reseaux=sous_reseaux,
            ports=reglage.ports,
            duree_s=duree_s,
            candidats=[
                CandidatLu(
                    ip=str(c.ip),
                    port=c.port,
                    statut_rtsp=c.statut_rtsp,
                    serveur=c.serveur,
                    camera=connues.get((c.ip, c.port)),
                )
                for c in candidats
            ],
        )

    return routes


def _routes_essai(
    apercus: Apercus,
    configuration: Configuration,
    hote_pont: str,
    base: Callable[[], Iterator[Session]],
    administrateur_connecte: Callable,
) -> APIRouter:
    """Essai d'un Candidat et son Aperçu, réservés à une session valide : un inconnu du réseau ne s'en sert
    pas pour deviner des mots de passe.

    Un seul essai à la fois, et seulement vers le réseau local, jamais vers ArgOS. Un nouvel essai retire
    le précédent et son Aperçu. L'URL du Flux (identifiants compris) reste côté serveur, jamais journalisée ;
    la Caméra est créée à partir d'elle.
    """
    Base = Annotated[Session, Depends(base)]
    routes = APIRouter(prefix="/api/essai", dependencies=[Depends(administrateur_connecte)])
    un_seul = threading.Lock()

    @routes.post("")
    def essayer(demande: DemandeEssai) -> EssaiLu:
        if not any(demande.ip in reseau for reseau in RESEAUX_LOCAUX):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, HORS_RESEAU_LOCAL)
        if not un_seul.acquire(blocking=False):
            raise HTTPException(status.HTTP_409_CONFLICT, ESSAI_EN_COURS)
        try:
            if demande.ip in soi.adresses_des_conteneurs([hote_pont]) or soi.publient_cette_api(
                [demande.ip], DELAI_DETECTION_S
            ):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, ADRESSE_D_ARGOS)
            generation = apercus.debuter()
            resultat = essai.essayer(
                demande.ip,
                demande.port,
                configuration.delai_sonde,
                identifiant=demande.identifiant,
                mot_de_passe=demande.mot_de_passe,
                chemin=demande.chemin,
            )
            journal_essai.info(
                "Essai : %s:%s issue %s chemin %s codec %s",
                demande.ip, demande.port, resultat.issue.value, resultat.chemin, resultat.codec,
            )
            apercu = None
            if resultat.issue == essai.Issue.FLUX_TROUVE:
                try:
                    apercu = apercus.ouvrir(generation, resultat)
                except EssaiAnnule:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Essai annulé pendant la recherche du Flux.") from None
                except OSError:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE, "Le pont MediaMTX n'a pas ouvert l'Aperçu."
                    ) from None
        finally:
            un_seul.release()
        return EssaiLu(
            issue=resultat.issue,
            chemin=resultat.chemin,
            codec=resultat.codec,
            apercu=apercu,
            expiration_s=configuration.expiration_apercu,
        )

    @routes.post("/renouveler", status_code=status.HTTP_204_NO_CONTENT)
    def renouveler() -> None:
        with _sans_apercu_404():
            apercus.renouveler()

    @routes.delete("", status_code=status.HTTP_204_NO_CONTENT)
    def retirer() -> None:
        apercus.annuler()

    @routes.post("/camera", status_code=status.HTTP_201_CREATED)
    def ajouter(ajout: AjoutDepuisEssai, base: Base) -> CameraLue:
        def creer(url: str) -> CameraLue:
            # Doublon : l'essai reste ouvert, l'Administrateur corrige le nom.
            with _erreurs_cameras():
                return cameras.creer(base, NouvelleCamera(nom=ajout.nom, url_rtsp=url, emplacement=ajout.emplacement))

        with _sans_apercu_404():
            return apercus.ajouter(creer)

    return routes


@contextmanager
def _sans_apercu_404() -> Iterator[None]:
    try:
        yield
    except AucunApercu:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun essai en cours avec un Flux trouvé.") from None


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
