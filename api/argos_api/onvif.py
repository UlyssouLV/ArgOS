"""Client ONVIF du Site : lit les Réglages de la Caméra (Horloge de son Appareil, Incrustations) sur la caméra.

L'appelant donne l'URL RTSP de la Caméra et le port ONVIF retenu ; il reçoit les Réglages lus et le port qui a
répondu, ou une `ErreurOnvif` avec son code. SOAP, recherche du port, profils et tokens restent ici.

- Port : celui retenu s'il répond encore en SOAP, sinon recherche sur les ports courants, dans leur ordre.
- Identifiants : ceux de l'URL RTSP, en WS-Security (empreinte) ; aucun si l'URL n'en a pas.
- Incrustations : celles de la première source vidéo (premier profil média).

WSDL ONVIF d'`onvif-zeep` (licence MIT, `wsdl/LICENSE`), lus par `zeep` : `onvif-zeep` n'est publié qu'en
sources, et l'image de l'API n'installe que des roues.
"""

import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

import requests
import zeep
from pydantic import BaseModel
from zeep.exceptions import Error as ErreurZeep
from zeep.exceptions import Fault, TransportError
from zeep.transports import Transport
from zeep.wsdl import Document
from zeep.wsse.username import UsernameToken

from argos_api import fuseaux

# Ports ONVIF courants, dans l'ordre de recherche : 8899 est celui des caméras XiongMai.
PORTS_ONVIF = (80, 8899, 2000, 8000, 8080)
CHEMIN_APPAREIL = "/onvif/device_service"
# Délais courts : une caméra du réseau local répond vite, ou ne répondra pas.
DELAI_CONNEXION_S = 2
DELAI_REPONSE_S = 4

DOSSIER_WSDL = Path(__file__).parent / "wsdl"
SOAP_12 = "http://www.w3.org/2003/05/soap-envelope"
SOAP_11 = "http://schemas.xmlsoap.org/soap/envelope/"
DEMANDE_HEURE = (
    f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="{SOAP_12}"><s:Body>'
    '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>'
).encode()

journal = logging.getLogger("argos_api.onvif")

CodeErreur = Literal["sans_onvif", "identifiants_refuses", "injoignable"]
Position = Literal["UpperLeft", "UpperRight", "LowerLeft", "LowerRight", "Custom"]


class ErreurOnvif(Exception):
    def __init__(self, code: CodeErreur) -> None:
        super().__init__(code)
        self.code = code


class Horloge(BaseModel):
    # Date et heure UTC de la caméra, et son écart avec l'heure du Site (positif : la caméra avance).
    date_heure_utc: datetime
    ecart_s: float
    # Fuseau tel que la caméra le donne (POSIX), et son nom IANA s'il est reconnu.
    fuseau_posix: str | None
    fuseau: str | None
    mode: Literal["manuel", "ntp"]
    serveur_ntp: str | None


class IncrustationNom(BaseModel):
    affichee: bool
    texte: str | None
    position: Position | None
    # La caméra annonce savoir recréer cette Incrustation (`GetOSDOptions`).
    peut_etre_reaffichee: bool


class IncrustationDateHeure(BaseModel):
    affichee: bool
    format: str | None
    position: Position | None
    peut_etre_reaffichee: bool


class Incrustations(BaseModel):
    nom: IncrustationNom
    date_heure: IncrustationDateHeure


class Reglages(BaseModel):
    horloge: Horloge
    incrustations: Incrustations


def lire_reglages(
    url_rtsp: str, port_retenu: int | None, maintenant: Callable[[], datetime]
) -> tuple[Reglages, int]:
    """Réglages lus sur la caméra de `url_rtsp`, et port ONVIF qui a répondu. Lève `ErreurOnvif`."""
    morceaux = urlsplit(url_rtsp)
    hote = morceaux.hostname or ""
    identifiants = (unquote(morceaux.username), unquote(morceaux.password or "")) if morceaux.username else None
    port = _trouver_port(hote, port_retenu)
    with _erreurs_onvif():
        reglages = _Camera(hote, port, identifiants).lire(maintenant)
    return reglages, port


# --- Recherche du port ------------------------------------------------------------------------------------------


class _Sonde(Enum):
    SOAP = "soap"
    # L'hôte répond (connexion refusée, page web…) mais pas en SOAP.
    AUTRE = "autre"
    MUET = "muet"


def _trouver_port(hote: str, port_retenu: int | None) -> int:
    if port_retenu is not None and _sonder(hote, port_retenu) is _Sonde.SOAP:
        return port_retenu
    with ThreadPoolExecutor(len(PORTS_ONVIF)) as sondes:
        resultats = list(sondes.map(lambda port: _sonder(hote, port), PORTS_ONVIF))
    for port, resultat in zip(PORTS_ONVIF, resultats, strict=True):
        if resultat is _Sonde.SOAP:
            return port
    raise ErreurOnvif("sans_onvif" if _Sonde.AUTRE in resultats else "injoignable")


def _sonder(hote: str, port: int) -> _Sonde:
    """`GetSystemDateAndTime` sans identifiants : seule une enveloppe SOAP prouve ONVIF, pas un `200` HTML."""
    try:
        reponse = requests.post(
            f"http://{hote}:{port}{CHEMIN_APPAREIL}",
            data=DEMANDE_HEURE,
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=(DELAI_CONNEXION_S, DELAI_REPONSE_S),
            allow_redirects=False,
        )
    except requests.ConnectionError as erreur:
        return _Sonde.AUTRE if _connexion_refusee(erreur) else _Sonde.MUET
    except requests.Timeout:
        return _Sonde.MUET
    except requests.RequestException:
        return _Sonde.AUTRE
    try:
        racine = ET.fromstring(reponse.content)
    except ET.ParseError:
        return _Sonde.AUTRE
    return _Sonde.SOAP if racine.tag in (f"{{{SOAP_12}}}Envelope", f"{{{SOAP_11}}}Envelope") else _Sonde.AUTRE


def _connexion_refusee(erreur: BaseException) -> bool:
    """Refus de connexion : l'hôte est là, rien n'écoute sur ce port."""
    vue: set[int] = set()
    cause: BaseException | None = erreur
    while cause is not None and id(cause) not in vue:
        if isinstance(cause, ConnectionRefusedError):
            return True
        vue.add(id(cause))
        cause = cause.__cause__ or cause.__context__ or next(
            (argument for argument in getattr(cause, "args", ()) if isinstance(argument, BaseException)), None
        )
    return False


# --- Lecture ----------------------------------------------------------------------------------------------------


class _JetonDecale(UsernameToken):
    """UsernameToken en empreinte, daté à l'heure de la caméra : certaines refusent un jeton daté de trop loin."""

    def __init__(self, identifiant: str, mot_de_passe: str, decalage: timedelta) -> None:
        super().__init__(identifiant, mot_de_passe, use_digest=True)
        self.decalage = decalage

    def apply(self, envelope: Any, headers: Any) -> Any:
        self.created = datetime.now(UTC) + self.decalage
        try:
            return super().apply(envelope, headers)
        finally:
            self.created = None


@cache
def _wsdl(nom: str) -> Document:
    return Document(str(DOSSIER_WSDL / f"{nom}.wsdl"), Transport(), settings=_reglages_zeep())


def _reglages_zeep() -> zeep.Settings:
    # Caméras peu rigoureuses : un champ manquant ou en trop ne fait pas échouer la lecture.
    return zeep.Settings(strict=False, xml_huge_tree=True)


def _service(wsdl: str, liaison: str, adresse: str, jeton: UsernameToken | None) -> Any:
    transport = Transport(timeout=DELAI_REPONSE_S, operation_timeout=(DELAI_CONNEXION_S, DELAI_REPONSE_S))
    client = zeep.Client(_wsdl(wsdl), wsse=jeton, transport=transport, settings=_reglages_zeep())
    return client.create_service(liaison, adresse)


class _Camera:
    def __init__(self, hote: str, port: int, identifiants: tuple[str, str] | None) -> None:
        self.adresse = f"http://{hote}:{port}{CHEMIN_APPAREIL}"
        self.identifiants = identifiants

    def lire(self, maintenant: Callable[[], datetime]) -> Reglages:
        appareil = _service("devicemgmt", "{http://www.onvif.org/ver10/device/wsdl}DeviceBinding", self.adresse, None)
        heure = appareil.GetSystemDateAndTime()
        date_heure_utc = _date_heure_utc(heure)
        jeton = None
        if self.identifiants is not None:
            jeton = _JetonDecale(*self.identifiants, decalage=date_heure_utc - datetime.now(UTC))
        appareil = _service("devicemgmt", "{http://www.onvif.org/ver10/device/wsdl}DeviceBinding", self.adresse, jeton)
        ntp = appareil.GetNTP()
        adresse_media = appareil.GetCapabilities(Category="Media").Media.XAddr
        media = _service("media", "{http://www.onvif.org/ver10/media/wsdl}MediaBinding", adresse_media, jeton)
        source = media.GetProfiles()[0].VideoSourceConfiguration.token
        osds = media.GetOSDs(ConfigurationToken=source)
        options = media.GetOSDOptions(ConfigurationToken=source).OSDOptions
        fuseau_posix = heure.TimeZone.TZ if heure.TimeZone is not None else None
        return Reglages(
            horloge=Horloge(
                date_heure_utc=date_heure_utc,
                ecart_s=(date_heure_utc - maintenant()).total_seconds(),
                fuseau_posix=fuseau_posix,
                fuseau=fuseaux.nom_lisible(fuseau_posix) if fuseau_posix else None,
                mode="ntp" if heure.DateTimeType == "NTP" else "manuel",
                serveur_ntp=_serveur_ntp(ntp),
            ),
            incrustations=_incrustations(osds or [], options),
        )


def _date_heure_utc(heure: Any) -> datetime:
    utc = heure.UTCDateTime
    return datetime(
        utc.Date.Year, utc.Date.Month, utc.Date.Day, utc.Time.Hour, utc.Time.Minute, utc.Time.Second, tzinfo=UTC
    )


def _serveur_ntp(ntp: Any) -> str | None:
    serveurs = (ntp.NTPFromDHCP if ntp.FromDHCP else ntp.NTPManual) or []
    for serveur in serveurs:
        nom = {"DNS": serveur.DNSname, "IPv4": serveur.IPv4Address, "IPv6": serveur.IPv6Address}.get(serveur.Type)
        if nom:
            return nom
    return None


def _incrustations(osds: list[Any], options: Any) -> Incrustations:
    textes = [osd for osd in osds if osd.TextString is not None]
    nom = next((osd for osd in textes if osd.TextString.Type == "Plain"), None)
    date_heure = next((osd for osd in textes if osd.TextString.Type in ("DateAndTime", "Date", "Time")), None)
    creables = set(options.TextOption.Type or []) if options.TextOption is not None else set()
    return Incrustations(
        nom=IncrustationNom(
            affichee=nom is not None,
            texte=nom.TextString.PlainText if nom else None,
            position=_position(nom),
            peut_etre_reaffichee="Plain" in creables,
        ),
        date_heure=IncrustationDateHeure(
            affichee=date_heure is not None,
            format=_format(date_heure),
            position=_position(date_heure),
            peut_etre_reaffichee="DateAndTime" in creables,
        ),
    )


def _position(osd: Any) -> Position | None:
    if osd is None:
        return None
    position = osd.Position.Type
    return position if position in ("UpperLeft", "UpperRight", "LowerLeft", "LowerRight") else "Custom"


def _format(osd: Any) -> str | None:
    if osd is None:
        return None
    return " ".join(f for f in (osd.TextString.DateFormat, osd.TextString.TimeFormat) if f) or None


# --- Erreurs ----------------------------------------------------------------------------------------------------


@contextmanager
def _erreurs_onvif() -> Iterator[None]:
    """Traduit les erreurs de zeep et du réseau en codes : la caméra a pu cesser de répondre en cours de lecture."""
    try:
        yield
    except (requests.ConnectionError, requests.Timeout) as erreur:
        raise ErreurOnvif("injoignable") from erreur
    except (ErreurZeep, requests.RequestException, AttributeError, IndexError, TypeError, ValueError) as erreur:
        if _identifiants_refuses(erreur):
            raise ErreurOnvif("identifiants_refuses") from erreur
        # Réponse inattendue (faute, champ absent) : la caméra ne répond pas en ONVIF comme ArgOS l'attend.
        journal.warning("ONVIF : réponse inattendue : %r", erreur)
        raise ErreurOnvif("sans_onvif") from erreur


def _identifiants_refuses(erreur: BaseException) -> bool:
    if isinstance(erreur, TransportError):
        return erreur.status_code in (401, 403)
    if isinstance(erreur, Fault):
        texte = " ".join(str(morceau) for morceau in (erreur.message, erreur.code, *(erreur.subcodes or [])))
        return "notauthorized" in texte.lower().replace(" ", "")
    return False
