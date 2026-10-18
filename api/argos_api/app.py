"""API du Site : connexion de l'Administrateur, gestion et Détection des Caméras, surveillance de leur état et pont MediaMTX."""

import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from ipaddress import IPv4Address, IPv4Network
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from argos_api import cameras, detection, essai, fuseaux, onvif, sessions, soi, sonde
from argos_api.apercu import Apercus, AucunApercu, EssaiAnnule
from argos_api.boucle import BoucleDeFond
from argos_api.cameras import AdresseMiseAJour, CameraCorrespondante, CameraLue, ModificationCamera, NouvelleCamera
from argos_api.configuration import Configuration, ReglageDetection, charger
from argos_api.ecoute import SortieSeulement
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
# Réseau local : seules ces adresses (RFC 1918) peuvent être essayées. Plages jamais jointes, seulement
# comparées à l'IP demandée.
RESEAUX_LOCAUX = [IPv4Network(r) for r in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]  # NOSONAR
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
    # MAC de l'Appareil, `aa:bb:cc:dd:ee:ff` ; `None` : illisible (hors du réseau local direct).
    mac: str | None
    # Caméra du Site (active ou désactivée) du même Appareil (MAC), sinon à la même IP résolue et au même
    # port ; `None` : nouveau.
    camera: CameraCorrespondante | None
    # Appareil connu vu à une autre IP : hôte de l'URL de ses Caméras mis à jour par cette Détection.
    adresse_mise_a_jour: AdresseMiseAJour | None
    # Caméra qui occupe la nouvelle URL : celle de l'Appareil n'a pas été modifiée.
    conflit: CameraCorrespondante | None


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
    # MAC de l'Appareil dès qu'il a répondu ; `None` si injoignable ou illisible.
    mac: str | None
    # Autre Caméra du même Appareil (même MAC, autre chemin) : l'UI avertit, l'ajout reste permis.
    appareil_deja_connu: CameraCorrespondante | None
    # Sans `POST /api/essai/renouveler` pendant ce délai, l'Aperçu est retiré.
    expiration_s: float


class DejaConfiguree(BaseModel):
    """`409` d'un essai sur l'adresse d'une Caméra du Site : `detail` à afficher tel quel."""

    detail: str
    camera: CameraCorrespondante


# Messages des `502` des Réglages de la Caméra, par code : l'UI affiche `detail` tel quel.
MESSAGES_ONVIF: dict[onvif.CodeErreur, str] = {
    "sans_onvif": "Cette caméra ne répond pas en ONVIF.",
    "identifiants_refuses": "La caméra refuse ces identifiants en ONVIF.",
    "injoignable": "Caméra injoignable.",
    "certificat_change": "Le certificat de cette caméra a changé.",
    "https_indisponible": "Cette caméra ne répond plus en HTTPS : ArgOS refuse de la régler en clair.",
    "en_clair_non_accepte": "Cette caméra ne propose pas HTTPS : ONVIF en clair non accepté.",
}


class ErreurOnvifLue(BaseModel):
    """`502` des Réglages de la Caméra : `code` pour l'UI, `detail` à afficher tel quel."""

    code: onvif.CodeErreur
    detail: str
    # `certificat_change` : les deux empreintes, pour trancher.
    certificat: cameras.CertificatsCompares | None = None


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
        surveillance = Surveillance(
            ouvrir_base, sonde.sonder, cameras.mac_a_l_adresse, configuration.delai_sonde, horloge
        )

        def reconcilier() -> None:
            with ouvrir_base() as base:
                actives = cameras.relais_actifs(base)
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
    # L'UI et l'API partagent l'origine HTTPS servie par web (ADR 0005) : pas de CORS.
    # Refuse avant routage et session.
    adresses_reseau_cameras = configuration.adresses_reseau_cameras()
    app.add_middleware(SortieSeulement, adresses=adresses_reseau_cameras)

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
        reponse.set_cookie(COOKIE_SESSION, jeton, secure=True, httponly=True, samesite="lax")
        return reponse

    @app.get(
        "/api/session", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(administrateur_connecte)]
    )
    def verifier_session() -> None:
        """`204` si la session du cookie est valide, `401` sinon : nginx l'appelle avant tout relais d'un Flux (ADR 0006)."""

    @app.delete("/api/session", status_code=status.HTTP_204_NO_CONTENT)
    def se_deconnecter(base: Base, jeton: JetonSession = None) -> Response:
        if jeton is not None:
            sessions.fermer(base, jeton)
        reponse = Response(status_code=status.HTTP_204_NO_CONTENT)
        reponse.delete_cookie(COOKIE_SESSION, secure=True, httponly=True, samesite="lax")
        return reponse

    @app.get("/api/moi")
    def moi(identifiant: Annotated[str, Depends(administrateur_connecte)]) -> Moi:
        return Moi(identifiant=identifiant)

    @app.get(soi.CHEMIN_INSTANCE)
    def instance() -> Instance:
        """Identité de cette instance, sans session : la Détection s'y reconnaît (argos_api/soi.py)."""
        return Instance(instance=soi.JETON_INSTANCE)

    @app.exception_handler(onvif.ErreurOnvif)
    def erreur_onvif(_: Request, erreur: onvif.ErreurOnvif) -> JSONResponse:
        """`502` des Réglages de la Caméra : la caméra n'a pas pu être lue ou réglée par ONVIF."""
        certificat = erreur.certificats if isinstance(erreur, cameras.CertificatChange) else None
        lue = ErreurOnvifLue(code=erreur.code, detail=MESSAGES_ONVIF[erreur.code], certificat=certificat)
        # `certificat` absent hors `certificat_change`.
        return JSONResponse(lue.model_dump(mode="json", exclude_none=True), status_code=status.HTTP_502_BAD_GATEWAY)

    @app.get("/api/fuseaux", dependencies=[Depends(administrateur_connecte)])
    def lister_fuseaux() -> list[str]:
        """Fuseaux proposés dans les Réglages de la Caméra : ceux que la lecture sait renommer, Europe/Paris en tête."""
        return list(fuseaux.FUSEAUX_COURANTS)

    app.include_router(
        _routes_cameras(base, administrateur_connecte, horloge, Path(configuration.enregistrements))
    )
    hote_pont = urlsplit(configuration.url_api_mediamtx).hostname or ""

    def adresses_d_argos() -> set[IPv4Address]:
        """Adresses de l'API et du pont, celles d'ArgOS sur le réseau des caméras comprises : jamais Candidat."""
        return soi.adresses_des_conteneurs([hote_pont]) | adresses_reseau_cameras

    app.include_router(
        _routes_detection(
            configuration.reglage_detection(), configuration.port_https, adresses_d_argos, base, administrateur_connecte
        )
    )
    app.include_router(_routes_essai(apercus, configuration, adresses_d_argos, base, administrateur_connecte))
    return app


def _journaux_sur_la_sortie() -> None:
    """uvicorn ne journalise que ses propres messages : ceux d'ArgOS (dès INFO) vont aussi sur la sortie."""
    racine = logging.getLogger("argos_api")
    if not racine.handlers:
        sortie = logging.StreamHandler()
        sortie.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        racine.addHandler(sortie)
        racine.setLevel(logging.INFO)


def _routes_cameras(
    base: Callable[[], Iterator[Session]],
    administrateur_connecte: Callable,
    horloge: Horloge,
    racine_enregistrements: Path,
) -> APIRouter:
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
            cameras.supprimer(base, id_camera, racine_enregistrements)

    @routes.get(
        "/{id_camera}/reglages",
        response_model=cameras.ReglagesLus,
        responses={status.HTTP_502_BAD_GATEWAY: {"model": ErreurOnvifLue}},
    )
    def lire_reglages(id_camera: int, base: Base) -> cameras.ReglagesLus:
        """Réglages lus sur la caméra à chaque appel, jamais gardés en base (seuls le contact ONVIF et la clé du
        Certificat de l'Appareil le sont), avec la sécurité de l'échange."""
        with _erreurs_cameras():
            return cameras.lire_reglages(base, id_camera, horloge)

    @routes.patch(
        "/{id_camera}/reglages",
        response_model=onvif.ResultatModification,
        responses={status.HTTP_502_BAD_GATEWAY: {"model": ErreurOnvifLue}},
    )
    def modifier_reglages(
        id_camera: int, modification: onvif.ModificationReglages, base: Base
    ) -> onvif.ResultatModification:
        """Envoie seulement les champs reçus, chacun séparément, puis relit la caméra : statut de chaque champ.

        `422` sans rien envoyer si une valeur sort des options relues sur la caméra (bornes, modes proposés)."""
        with _erreurs_cameras():
            return cameras.modifier_reglages(base, id_camera, modification, horloge)

    @routes.post(
        "/{id_camera}/reglages/mise-a-l-heure",
        response_model=onvif.Horloge,
        responses={status.HTTP_502_BAD_GATEWAY: {"model": ErreurOnvifLue}},
    )
    def mettre_a_l_heure(id_camera: int, base: Base) -> onvif.Horloge:
        """Envoie une fois l'heure UTC du serveur à la caméra (mode manuel, fuseau gardé), puis relit son Horloge."""
        with _erreurs_cameras():
            return cameras.mettre_a_l_heure(base, id_camera, horloge)

    @routes.post(
        "/{id_camera}/reglages/certificat",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={status.HTTP_502_BAD_GATEWAY: {"model": ErreurOnvifLue}},
    )
    def faire_confiance(id_camera: int, confiance: cameras.ConfianceCertificat, base: Base) -> None:
        """« Faire confiance au nouveau certificat » : seulement à l'empreinte que la caméra présente encore."""
        with _erreurs_cameras():
            cameras.faire_confiance(base, id_camera, confiance.empreinte, horloge)

    @routes.delete("/{id_camera}/reglages/certificat", status_code=status.HTTP_204_NO_CONTENT)
    def oublier_certificat(id_camera: int, base: Base) -> None:
        """« Oublier le certificat de cette caméra » : le contact suivant repart de zéro."""
        with _erreurs_cameras():
            cameras.oublier_certificat(base, id_camera)

    @routes.put("/{id_camera}/reglages/onvif-en-clair", status_code=status.HTTP_204_NO_CONTENT)
    def accepter_en_clair(id_camera: int, base: Base) -> None:
        """« Régler quand même en clair » : une caméra sans HTTPS est ensuite réglée en HTTP."""
        with _erreurs_cameras():
            cameras.accepter_en_clair(base, id_camera, accepte=True)

    @routes.delete("/{id_camera}/reglages/onvif-en-clair", status_code=status.HTTP_204_NO_CONTENT)
    def retirer_en_clair(id_camera: int, base: Base) -> None:
        """Retire l'accord ONVIF en clair : seule la sonde repart en HTTP."""
        with _erreurs_cameras():
            cameras.accepter_en_clair(base, id_camera, accepte=False)

    return routes


def _routes_detection(
    reglage: ReglageDetection,
    port_https: int,
    adresses_d_argos: Callable[[], set[IPv4Address]],
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
            trouves = detection.detecter(reglage.sous_reseaux, reglage.ports, adresses_d_argos(), DELAI_DETECTION_S)
            argos = soi.publient_cette_api({c.ip for c in trouves}, port_https, DELAI_DETECTION_S)
            candidats = [c for c in trouves if c.ip not in argos]
            duree_s = round(monotonic() - debut, 1)
        finally:
            une_seule.release()
        rapprochements = cameras.rapprocher(base, candidats)
        for c in candidats:
            journal.info("Détection : Candidat %s:%s RTSP %s Server %s", c.ip, c.port, c.statut_rtsp, c.serveur)
            rapprochement = rapprochements[c]
            if rapprochement.adresse_mise_a_jour is not None:
                ancienne = rapprochement.adresse_mise_a_jour.ancienne
                journal.info("Détection : Appareil %s suivi de %s à %s", c.mac, ancienne, c.ip)
            if rapprochement.conflit is not None:
                id_conflit = rapprochement.conflit.id
                journal.warning("Détection : Appareil %s vu à %s, URL déjà prise par la Caméra %s", c.mac, c.ip, id_conflit)
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
                    mac=c.mac,
                    **rapprochements[c].model_dump(),
                )
                for c in candidats
            ],
        )

    return routes


def _routes_essai(
    apercus: Apercus,
    configuration: Configuration,
    adresses_d_argos: Callable[[], set[IPv4Address]],
    base: Callable[[], Iterator[Session]],
    administrateur_connecte: Callable,
) -> APIRouter:
    """Essai d'un Candidat et son Aperçu, réservés à une session valide : un inconnu du réseau ne s'en sert
    pas pour deviner des mots de passe.

    Un seul essai à la fois, et seulement vers le réseau local, jamais vers ArgOS. Refusé après la sonde, sans
    Aperçu, pour une Caméra déjà configurée (même rapprochement que la Détection : un autre Appareil qui a repris
    son adresse reste essayable) ou un Flux déjà configuré sur le même Appareil (même MAC, même chemin), même si
    son IP a changé. Un nouvel essai retire le précédent et son Aperçu. L'URL du Flux (identifiants compris) reste côté serveur, jamais journalisée ;
    la Caméra est créée à partir d'elle.
    """
    Base = Annotated[Session, Depends(base)]
    routes = APIRouter(prefix="/api/essai", dependencies=[Depends(administrateur_connecte)])
    un_seul = threading.Lock()

    @routes.post("", response_model=EssaiLu, responses={status.HTTP_409_CONFLICT: {"model": DejaConfiguree}})
    def essayer(demande: DemandeEssai, base: Base) -> EssaiLu | JSONResponse:
        if not any(demande.ip in reseau for reseau in RESEAUX_LOCAUX):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, HORS_RESEAU_LOCAL)
        if not un_seul.acquire(blocking=False):
            raise HTTPException(status.HTTP_409_CONFLICT, ESSAI_EN_COURS)
        try:
            if demande.ip in adresses_d_argos() or soi.publient_cette_api(
                [demande.ip], configuration.port_https, DELAI_DETECTION_S
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
            chemin = resultat.chemin if resultat.issue == essai.Issue.FLUX_TROUVE else None
            correspondance = cameras.correspondance_de_l_essai(base, demande.ip, demande.port, resultat.mac, chemin)
            if correspondance is not None and correspondance.deja_configuree:
                return _deja_configuree(correspondance.camera)
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
            mac=resultat.mac,
            appareil_deja_connu=None if correspondance is None else correspondance.camera,
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
        def creer(resultat: essai.Resultat) -> CameraLue:
            # Doublon : l'essai reste ouvert, l'Administrateur corrige le nom.
            nouvelle = NouvelleCamera(nom=ajout.nom, url_rtsp=resultat.url, emplacement=ajout.emplacement)
            with _erreurs_cameras():
                return cameras.creer(base, nouvelle, mac=resultat.mac, codec=resultat.codec)

        with _sans_apercu_404():
            return apercus.ajouter(creer)

    return routes


def _deja_configuree(camera: CameraCorrespondante) -> JSONResponse:
    deja = DejaConfiguree(detail=f"Déjà configurée : {camera.nom}", camera=camera)
    return JSONResponse(deja.model_dump(), status_code=status.HTTP_409_CONFLICT)


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
    except cameras.EnregistrementRefuse:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Une Caméra désactivée ne peut pas enregistrer."
        ) from None
    except cameras.CertificatNonPresente:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La caméra ne présente plus ce certificat : rouvrir ses Réglages."
        ) from None
    except onvif.HorsDesOptions as erreur:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Valeur non proposée par la caméra : {erreur.champ}."
        ) from None
