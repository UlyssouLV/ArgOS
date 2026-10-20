"""Client ONVIF du Site : lit et modifie les Réglages de la Caméra (Horloge et Image de son Appareil, Incrustations,
Encodage de son Flux).

L'appelant donne l'URL RTSP de la Caméra, son codec connu et le contact retenu (schéma, port, empreinte de la clé
mémorisée) ; il
reçoit les Réglages lus (ou, après une modification, le résultat de chaque champ envoyé ; après une mise à l'heure
ou un calage, l'Horloge relue) et le contact qui a répondu, ou une `ErreurOnvif` avec son code.
SOAP, recherche du port, TLS, profils et tokens restent ici.

- Contact (docs/adr/0007-onvif-en-https-par-cle-memorisee.md) : HTTPS sur `443` d'abord, à chaque échange (une
  Caméra retenue en HTTP y passe dès que la caméra le propose) ; sinon le port HTTP retenu s'il répond encore en
  SOAP, sinon recherche sur les ports HTTP courants, dans leur ordre. Une Caméra retenue en HTTPS n'est jamais
  cherchée en HTTP : sans HTTPS, refus (`https_indisponible`).
- ONVIF en clair : en HTTP, seule la sonde (`GetSystemDateAndTime` sans identifiants) part sans l'accord de
  l'Administrateur ; sans lui, refus (`en_clair_non_accepte`).
- TLS : ni autorité, ni nom, ni expiration (certificats auto-signés, adressés par IP) ; la clé publique (SPKI) du
  Certificat de l'Appareil est comparée sur chaque connexion à celle mémorisée, ou, au premier contact, à la
  première vue dans l'échange. TLS 1.0 minimum, pour ce seul client.
- Adresses de service : seul le chemin des `XAddr` annoncés sert ; schéma, hôte et port sont ceux du contact.
- Identifiants : ceux de l'URL RTSP, en WS-Security (empreinte) ; aucun si l'URL n'en a pas.
- Incrustations : celles de la première source vidéo (premier profil média).
- Image : celle de la source vidéo du profil de la Caméra (la première sans profil retrouvé), par le service image
  (`ver20/imaging`). Un paramètre absent de
  `GetOptions` n'est ni lu ni proposé ; un niveau sans bornes annoncées non plus (mode seul). Sans service image, ou
  s'il répond en faute, l'Image est non réglable, et le reste des Réglages est lu quand même. Une valeur hors des
  options relues est refusée (`HorsDesOptions`) avant tout envoi, pour toute la modification.
- Encodage (docs/adr/0008-encodage-par-media-2-media-1-seulement-en-h264.md) : celui du profil dont l'URL de flux
  (`GetStreamUri`, RTSP) a le chemin et la requête de l'URL RTSP de la Caméra (hôte, port et identifiants ignorés) ;
  aucun : `profil_introuvable`. Par le média 2 si `GetServices` l'annonce, sinon par le média 1 seulement si le codec
  connu de la Caméra est `H264` ; sinon `non_reglable`, valeurs en lecture seule. Seuls résolution, images par seconde
  et débit max changent : codec, qualité et intervalle entre images clés relus repartent tels quels. Une valeur hors
  des options relues est refusée (`HorsDesOptions`) avant tout envoi. Envoyé en dernier (il coupe le Flux), puis la
  caméra est relue toutes les `PAS_RELECTURE_S` jusqu'à ce qu'elle réponde, `DELAI_RELECTURE_S` au plus ; sans
  réponse, chaque champ envoyé est `pas_pris` (`sans_reponse`) et les Réglages rendus sont ceux lus avant l'envoi.
- Horloge : le fuseau part seul, en gardant le mode et l'heure de la caméra ; la mise à l'heure du Site passe la
  caméra en mode manuel, à l'heure UTC du serveur, en gardant son fuseau. Le calage
  (docs/adr/0014-serveur-de-temps-du-site.md) règle le serveur NTP manuel (jamais `FromDHCP`) sur le Serveur de
  temps du Site, puis le mode NTP au fuseau du Site ; sa vérification relit l'Horloge seule (service appareil).
- Modification : chaque `Set…` part seul (un refus n'empêche pas les autres ; un paramètre d'image par
  `SetImagingSettings`, le niveau avec son mode), puis la caméra est relue une fois : un champ
  est `pris` si la valeur relue est celle demandée, `pas_pris` sinon, `refuse` si la caméra (ou ArgOS, quand
  elle n'annonce pas savoir recréer une Incrustation) l'a refusé.

WSDL ONVIF d'`onvif-zeep` (licence MIT, `wsdl/LICENSE`), lus par `zeep` : `onvif-zeep` n'est publié qu'en
sources, et l'image de l'API n'installe que des roues. Le média 2, absent d'`onvif-zeep`, vient d'onvif.org
(`wsdl/media2/` : `media2.wsdl`, `onvif.xsd` et `common.xsd` de son époque, enveloppe SOAP 1.2 du W3C), imports
rendus locaux.
"""

import hashlib
import logging
import ssl
import time
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import cache, cached_property
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

import requests
import zeep
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from zeep.exceptions import Error as ErreurZeep
from zeep.exceptions import Fault, TransportError
from zeep.transports import Transport
from zeep.wsdl import Document
from zeep.wsse.username import UsernameToken

from argos_api import fuseaux

# HTTPS sondé d'abord, sur ce seul port.
PORT_HTTPS = 443
# Ports ONVIF HTTP courants, dans l'ordre de recherche : 8899 est celui des caméras XiongMai.
PORTS_ONVIF = (80, 8899, 2000, 8000, 8080)
# Versions TLS acceptées vers les caméras mais signalées « TLS ancien » (`ssl.SSLSocket.version()`).
VERSIONS_TLS_ANCIENNES = ("TLSv1", "TLSv1.1")
CHEMIN_APPAREIL = "/onvif/device_service"
# Délais courts : une caméra du réseau local répond vite, ou ne répondra pas.
DELAI_CONNEXION_S = 2
DELAI_REPONSE_S = 4
# Relecture après un envoi d'Encodage : la caméra relance son encodeur, et peut se taire quelques secondes.
PAS_RELECTURE_S = 2
DELAI_RELECTURE_S = 20
# Espaces de noms XML : des noms imposés par ONVIF, jamais appelés (NOSONAR définitif).
ESPACE_MEDIA_2 = "http://www.onvif.org/ver20/media/wsdl"  # NOSONAR
ESPACE_SCHEMA = "http://www.onvif.org/ver10/schema"  # NOSONAR

DOSSIER_WSDL = Path(__file__).parent / "wsdl"
SOAP_12 = "http://www.w3.org/2003/05/soap-envelope"
SOAP_11 = "http://schemas.xmlsoap.org/soap/envelope/"
DEMANDE_HEURE = (
    f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="{SOAP_12}"><s:Body>'
    '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>'
).encode()

journal = logging.getLogger("argos_api.onvif")
# Seul client sans vérification d'autorité, voulu (la clé est comparée à part) : urllib3 le signalerait à chaque
# requête.
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

CodeErreur = Literal[
    "sans_onvif", "identifiants_refuses", "injoignable", "certificat_change", "https_indisponible", "en_clair_non_accepte"
]
Schema = Literal["https", "http"]
Coin = Literal["UpperLeft", "UpperRight", "LowerLeft", "LowerRight"]
Position = Coin | Literal["Custom"]
CleIncrustation = Literal["nom", "date_heure"]
StatutChamp = Literal["pris", "pas_pris", "refuse"]
# `profil_introuvable` : aucun profil à l'URL RTSP de la Caméra ; `non_reglable` : ni média 2, ni Flux en H.264.
RaisonEncodage = Literal["profil_introuvable", "non_reglable"]
# `IrCutFilter` ONVIF : `ON` = filtre posé (jour), `OFF` = filtre retiré (nuit), `AUTO`.
ModeInfrarouge = Literal["ON", "OFF", "AUTO"]
ModeCompensation = Literal["OFF", "ON"]
# Paramètres d'image bornés : champ ArgOS → élément ONVIF (`ImagingSettings20`, `ImagingOptions20`).
PARAMETRES_IMAGE = {
    "luminosite": "Brightness",
    "contraste": "Contrast",
    "saturation": "ColorSaturation",
    "nettete": "Sharpness",
}
# Compensations à mode et niveau : champ ArgOS → élément ONVIF.
COMPENSATIONS_IMAGE = {"contre_jour": "BacklightCompensation", "wdr": "WideDynamicRange"}
# Type de texte ONVIF de chaque Incrustation, et son coin quand ArgOS la réaffiche sans coin demandé.
TYPES_TEXTE: dict[CleIncrustation, str] = {"nom": "Plain", "date_heure": "DateAndTime"}
COINS_PAR_DEFAUT: dict[CleIncrustation, Coin] = {"nom": "UpperLeft", "date_heure": "LowerLeft"}


class HorsDesOptions(Exception):
    """Valeur que la caméra n'annonce pas (hors bornes, mode ou paramètre non proposé) : rien n'a été envoyé."""

    def __init__(self, champ: str) -> None:
        super().__init__(champ)
        # Chemin du champ refusé : `image.luminosite`…
        self.champ = champ


class ErreurOnvif(Exception):
    def __init__(self, code: CodeErreur, empreinte_vue: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        # `certificat_change` : empreinte de la clé que la caméra présente.
        self.empreinte_vue = empreinte_vue


@dataclass(frozen=True)
class Retenu:
    """Ce que le Site a retenu de la caméra ; `None` : rien encore."""

    schema: Schema | None = None
    port: int | None = None
    # Empreinte SHA-256 (hexadécimal) de la clé publique du Certificat de l'Appareil, mémorisée au premier contact.
    empreinte: str | None = None
    # L'Administrateur accepte l'ONVIF en clair, pour une caméra sans HTTPS.
    en_clair_accepte: bool = False


@dataclass(frozen=True)
class Contact:
    """Schéma et port qui ont répondu ; en HTTPS, l'empreinte de la clé présentée et la version TLS négociée."""

    schema: Schema
    port: int
    empreinte: str | None = None
    version_tls: str | None = None

    @property
    def tls_ancien(self) -> bool:
        return self.version_tls in VERSIONS_TLS_ANCIENNES


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


class Bornes(BaseModel):
    min: float
    max: float

    def contient(self, valeur: float) -> bool:
        return self.min <= valeur <= self.max


class ValeursImage(BaseModel):
    """Image relue ; `None` : paramètre que la caméra ne propose pas."""

    infrarouge: ModeInfrarouge | None = None
    luminosite: float | None = None
    contraste: float | None = None
    saturation: float | None = None
    nettete: float | None = None
    contre_jour: ModeCompensation | None = None
    contre_jour_niveau: float | None = None
    wdr: ModeCompensation | None = None
    wdr_niveau: float | None = None


class OptionsImage(BaseModel):
    """Ce que la caméra propose : modes, ou bornes ; `None` : non proposé."""

    infrarouge: list[ModeInfrarouge] | None = None
    luminosite: Bornes | None = None
    contraste: Bornes | None = None
    saturation: Bornes | None = None
    nettete: Bornes | None = None
    contre_jour: list[ModeCompensation] | None = None
    contre_jour_niveau: Bornes | None = None
    wdr: list[ModeCompensation] | None = None
    wdr_niveau: Bornes | None = None


class Image(BaseModel):
    """Image de l'Appareil (source vidéo du profil de la Caméra), partagée par toutes ses Caméras."""

    reglable: bool
    # `non_reglable` : pas de service image, ou il répond en faute.
    raison: Literal["non_reglable"] | None = None
    valeurs: ValeursImage | None = None
    options: OptionsImage | None = None


IMAGE_NON_REGLABLE = Image(reglable=False, raison="non_reglable")


class ValeursEncodage(BaseModel):
    """Encodage relu ; `None` : valeur que la caméra ne donne pas."""

    # `largeur`x`hauteur`, en pixels.
    resolution: str
    images_par_seconde: float | None = None
    # kbit/s.
    debit_max: int | None = None
    codec: str
    qualite: float | None = None
    intervalle_images_cles: int | None = None


class OptionsEncodage(BaseModel):
    """Ce que la caméra propose ; `None` : non proposé (pas réglable)."""

    resolutions: list[str]
    images_par_seconde: Bornes | None = None
    debit_max: Bornes | None = None


class Encodage(BaseModel):
    """Encodage du Flux de la Caméra : celui du profil de son URL RTSP."""

    reglable: bool
    raison: RaisonEncodage | None = None
    # Nom du profil (`mainStream`…), ou son token s'il n'en a pas.
    profil: str | None = None
    valeurs: ValeursEncodage | None = None
    options: OptionsEncodage | None = None


ENCODAGE_PROFIL_INTROUVABLE = Encodage(reglable=False, raison="profil_introuvable")
ENCODAGE_NON_REGLABLE = Encodage(reglable=False, raison="non_reglable")


class Reglages(BaseModel):
    horloge: Horloge
    incrustations: Incrustations
    image: Image
    encodage: Encodage


class _ModificationIncrustation(BaseModel):
    """Champs modifiés d'une Incrustation ; un champ absent (ou `null`) n'est pas envoyé."""

    model_config = ConfigDict(extra="forbid")

    affichee: bool | None = None
    position: Coin | None = None

    @model_validator(mode="after")
    def _cacher_seule(self) -> "_ModificationIncrustation":
        # Une Incrustation cachée n'a plus ni texte ni coin : rien d'autre à régler en même temps.
        if self.affichee is False and len(self.model_dump(exclude_none=True)) > 1:
            raise ValueError("Cacher une Incrustation ne se combine avec aucun autre champ de celle-ci")
        return self


class ModificationNom(_ModificationIncrustation):
    texte: str | None = None


class ModificationDateHeure(_ModificationIncrustation):
    """Le format de la date et heure ne s'envoie jamais : les caméras ne le règlent pas de façon fiable."""


class ModificationIncrustations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: ModificationNom | None = None
    date_heure: ModificationDateHeure | None = None


class ModificationHorloge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Nom IANA (`Europe/Paris`) : ArgOS l'envoie en POSIX.
    fuseau: str | None = None

    @field_validator("fuseau")
    @classmethod
    def _fuseau_connu(cls, fuseau: str | None) -> str | None:
        if fuseau is not None and not fuseaux.connu(fuseau):
            raise ValueError("Fuseau IANA inconnu")
        return fuseau


class ModificationImage(BaseModel):
    """Champs d'Image modifiés ; un champ absent (ou `null`) n'est pas envoyé. Bornes : celles relues sur la caméra."""

    model_config = ConfigDict(extra="forbid")

    infrarouge: ModeInfrarouge | None = None
    luminosite: float | None = None
    contraste: float | None = None
    saturation: float | None = None
    nettete: float | None = None
    contre_jour: ModeCompensation | None = None
    contre_jour_niveau: float | None = None
    wdr: ModeCompensation | None = None
    wdr_niveau: float | None = None


class ModificationEncodage(BaseModel):
    """Champs d'Encodage modifiés ; un champ absent (ou `null`) n'est pas envoyé. Options : celles relues."""

    model_config = ConfigDict(extra="forbid")

    resolution: str | None = None
    images_par_seconde: float | None = None
    debit_max: int | None = None


class ModificationReglages(BaseModel):
    """Seulement les champs que l'Administrateur a modifiés."""

    model_config = ConfigDict(extra="forbid")

    horloge: ModificationHorloge = ModificationHorloge()
    incrustations: ModificationIncrustations = ModificationIncrustations()
    image: ModificationImage = ModificationImage()
    encodage: ModificationEncodage = ModificationEncodage()


class ChampModifie(BaseModel):
    # Chemin du champ envoyé : `horloge.fuseau`, `incrustations.nom.texte`, `image.luminosite`…
    champ: str
    demande: str | bool | float
    # Valeur relue sur la caméra après l'envoi (fuseau : sa chaîne POSIX) ; `None` : sans valeur (Incrustation
    # cachée, caméra sans fuseau).
    relu: str | bool | float | None
    statut: StatutChamp
    # `sans_reponse` : la caméra n'a plus répondu après l'envoi d'Encodage ; rien n'a pu être relu.
    raison: Literal["sans_reponse"] | None = None


class ResultatModification(BaseModel):
    # Seulement les champs envoyés.
    champs: list[ChampModifie]
    # Réglages relus après l'envoi ; ceux d'avant si la caméra n'a plus répondu.
    reglages: Reglages


def lire_reglages(
    url_rtsp: str, retenu: Retenu, maintenant: Callable[[], datetime], codec: str | None
) -> tuple[Reglages, Contact]:
    """Réglages lus sur la caméra de `url_rtsp` (Flux en `codec`, s'il est connu), et contact qui a répondu.

    Lève `ErreurOnvif`.
    """
    camera, contact = _joindre(url_rtsp, retenu, codec)
    with _erreurs_onvif():
        return camera.lire(maintenant), contact


def modifier_reglages(
    url_rtsp: str,
    retenu: Retenu,
    modification: ModificationReglages,
    maintenant: Callable[[], datetime],
    codec: str | None,
) -> tuple[ResultatModification, Contact]:
    """Envoie chaque champ de `modification` à la caméra, la relit, et dit si chacun a été pris.

    Lève `ErreurOnvif`, ou `HorsDesOptions` sans rien envoyer.
    """
    camera, contact = _joindre(url_rtsp, retenu, codec)
    with _erreurs_onvif():
        return camera.modifier(modification, maintenant), contact


def mettre_a_l_heure(
    url_rtsp: str, retenu: Retenu, maintenant: Callable[[], datetime]
) -> tuple[Horloge, Contact]:
    """Met la caméra à l'heure du Site (mode manuel, fuseau gardé), puis relit son Horloge. Lève `ErreurOnvif`."""
    camera, contact = _joindre(url_rtsp, retenu)
    with _erreurs_onvif():
        return camera.mettre_a_l_heure(maintenant), contact


def lire_horloge(url_rtsp: str, retenu: Retenu, maintenant: Callable[[], datetime]) -> tuple[Horloge, Contact]:
    """Horloge lue sur la caméra (service appareil seul), et contact qui a répondu. Lève `ErreurOnvif`."""
    camera, contact = _joindre(url_rtsp, retenu)
    with _erreurs_onvif():
        return camera.lire_horloge(maintenant), contact


def caler(
    url_rtsp: str, retenu: Retenu, serveur_ntp: str, fuseau_posix: str, maintenant: Callable[[], datetime]
) -> tuple[Horloge, Contact]:
    """Cale la caméra sur le Serveur de temps du Site : serveur NTP manuel `serveur_ntp`, puis mode NTP au fuseau
    `fuseau_posix` ; relit son Horloge. Lève `ErreurOnvif` (un refus de la caméra compris)."""
    camera, contact = _joindre(url_rtsp, retenu)
    with _erreurs_onvif():
        return camera.caler(serveur_ntp, fuseau_posix, maintenant), contact


def _joindre(url_rtsp: str, retenu: Retenu, codec: str | None = None) -> tuple["_Camera", Contact]:
    morceaux = urlsplit(url_rtsp)
    hote = morceaux.hostname or ""
    identifiants = (unquote(morceaux.username), unquote(morceaux.password or "")) if morceaux.username else None
    tls = _contexte_tls(retenu.empreinte)
    session = _session(tls)
    contact = _trouver_contact(session, tls, hote, retenu)
    return _Camera(session, hote, contact, identifiants, _flux(url_rtsp), codec), contact


def _flux(url: str) -> tuple[str, str]:
    """Chemin et requête d'une URL RTSP : ce qui désigne un profil, quels que soient hôte, port et identifiants."""
    morceaux = urlsplit(url)
    return morceaux.path or "/", morceaux.query


def _adresse(contact: Contact, hote: str, chemin: str) -> str:
    return f"{contact.schema}://{hote}:{contact.port}{chemin}"


# --- TLS --------------------------------------------------------------------------------------------------------


class _ContexteTls(ssl.SSLContext):
    """Contexte TLS d'un échange avec une caméra : chaque connexion doit présenter la clé attendue.

    Attendue : celle mémorisée ; au premier contact, la première vue dans l'échange.
    """

    attendue: str | None
    # Version TLS de la dernière connexion (`TLSv1.3`…).
    version: str | None

    def wrap_socket(self, sock: Any, *args: Any, **kwargs: Any) -> ssl.SSLSocket:
        tls = super().wrap_socket(sock, *args, **kwargs)
        empreinte = empreinte_spki(tls.getpeercert(binary_form=True) or b"")
        if self.attendue is None:
            self.attendue = empreinte
        if empreinte != self.attendue:
            tls.close()
            # Hors des erreurs réseau : ni urllib3 ni zeep ne la retraduisent, rien d'autre ne part.
            raise ErreurOnvif("certificat_change", empreinte_vue=empreinte)
        self.version = tls.version()
        return tls


def _contexte_tls(attendue: str | None) -> _ContexteTls:
    contexte = _ContexteTls(ssl.PROTOCOL_TLS_CLIENT)
    # Ni autorité, ni nom, ni expiration : les caméras signent elles-mêmes, pour une IP. La clé est comparée à
    # chaque connexion (wrap_socket), docs/adr/0007-onvif-en-https-par-cle-memorisee.md.
    contexte.check_hostname = False
    contexte.verify_mode = ssl.CERT_NONE  # NOSONAR : clé du Certificat de l'Appareil comparée à chaque connexion
    # TLS 1.0 minimum pour ce seul client : un TLS ancien avec une clé mémorisée vaut mieux que du clair. OpenSSL 3
    # ne l'accepte qu'au niveau de sécurité 0.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        contexte.minimum_version = ssl.TLSVersion.TLSv1  # NOSONAR : caméras anciennes, signalées « TLS ancien »
    contexte.set_ciphers("DEFAULT:@SECLEVEL=0")  # NOSONAR : TLS 1.0 des caméras anciennes, ADR 0007
    contexte.attendue = attendue
    contexte.version = None
    return contexte


def empreinte_spki(certificat_der: bytes) -> str:
    """SHA-256 (hexadécimal) de la clé publique (SPKI) d'un certificat : stable quand la caméra le renouvelle."""
    cle = x509.load_der_x509_certificate(certificat_der).public_key()
    return hashlib.sha256(cle.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).hexdigest()


class _AdaptateurTls(HTTPAdapter):
    def __init__(self, contexte: ssl.SSLContext) -> None:
        self.contexte = contexte
        super().__init__()

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        super().init_poolmanager(*args, **kwargs, ssl_context=self.contexte)


def _session(contexte: _ContexteTls) -> requests.Session:
    """Session HTTP de l'échange : sonde et SOAP passent par le même contexte TLS."""
    session = requests.Session()
    session.mount("https://", _AdaptateurTls(contexte))
    # Sans autorité : le contexte compare la clé (urllib3 imposerait sinon la vérification par une autorité).
    session.verify = False  # NOSONAR : clé du Certificat de l'Appareil comparée à chaque connexion
    return session


# --- Recherche du contact ---------------------------------------------------------------------------------------


class _Sonde(Enum):
    SOAP = "soap"
    # L'hôte répond (connexion refusée, page web, TLS refusé…) mais pas en SOAP.
    AUTRE = "autre"
    MUET = "muet"


def empreinte_presentee(url_rtsp: str) -> str:
    """Empreinte de la clé publique du Certificat que la caméra de `url_rtsp` présente en ONVIF chiffré, sans rien
    envoyer d'authentifié. Lève `ErreurOnvif` si elle ne répond pas en ONVIF chiffré."""
    hote = urlsplit(url_rtsp).hostname or ""
    tls = _contexte_tls(None)
    sonde = _sonder(_session(tls), _adresse(Contact("https", PORT_HTTPS), hote, CHEMIN_APPAREIL))
    if sonde is not _Sonde.SOAP or tls.attendue is None:
        raise _https_absent(sonde)
    return tls.attendue


def _https_absent(sonde: _Sonde) -> ErreurOnvif:
    """Pas d'ONVIF chiffré : une caméra muette sur 443 est plutôt éteinte, sinon HTTPS lui manque."""
    return ErreurOnvif("injoignable" if sonde is _Sonde.MUET else "https_indisponible")


def _trouver_contact(session: requests.Session, tls: _ContexteTls, hote: str, retenu: Retenu) -> Contact:
    https = Contact("https", PORT_HTTPS)
    sonde_https = _sonder(session, _adresse(https, hote, CHEMIN_APPAREIL))
    if sonde_https is _Sonde.SOAP:
        return Contact("https", PORT_HTTPS, tls.attendue, tls.version)
    if retenu.schema == "https":
        # Pas de rétrogradation : un HTTPS disparu peut être filtré par qui veut lire l'échange en clair.
        raise _https_absent(sonde_https)
    http = _chercher_http(session, hote, retenu, sonde_https)
    if not retenu.en_clair_accepte:
        raise ErreurOnvif("en_clair_non_accepte")
    return http  # NOSONAR : HTTP seulement après accord de l'Administrateur, caméra sans HTTPS


def _chercher_http(session: requests.Session, hote: str, retenu: Retenu, sonde_https: _Sonde) -> Contact:
    """Port HTTP qui répond en SOAP : le retenu d'abord, sinon les ports courants. Rien que la sonde."""
    if retenu.schema == "http" and retenu.port is not None:
        http = Contact("http", retenu.port)
        if _sonder(session, _adresse(http, hote, CHEMIN_APPAREIL)) is _Sonde.SOAP:
            return http
    candidats = [Contact("http", port) for port in PORTS_ONVIF]
    with ThreadPoolExecutor(len(candidats)) as sondes:
        resultats = list(sondes.map(lambda c: _sonder(session, _adresse(c, hote, CHEMIN_APPAREIL)), candidats))
    for candidat, resultat in zip(candidats, resultats, strict=True):
        if resultat is _Sonde.SOAP:
            return candidat
    raise ErreurOnvif("sans_onvif" if _Sonde.AUTRE in (sonde_https, *resultats) else "injoignable")


def _sonder(session: requests.Session, adresse: str) -> _Sonde:
    """`GetSystemDateAndTime` sans identifiants : seule une enveloppe SOAP prouve ONVIF, pas un `200` HTML."""
    try:
        reponse = session.post(
            adresse,
            data=DEMANDE_HEURE,
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=(DELAI_CONNEXION_S, DELAI_REPONSE_S),
            allow_redirects=False,
        )
    except requests.exceptions.SSLError:
        return _Sonde.AUTRE
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


def _service(
    session: requests.Session, wsdl: str, liaison: str, adresse: str, jeton: UsernameToken | None
) -> Any:
    transport = Transport(
        session=session, timeout=DELAI_REPONSE_S, operation_timeout=(DELAI_CONNEXION_S, DELAI_REPONSE_S)
    )
    client = zeep.Client(_wsdl(wsdl), wsse=jeton, transport=transport, settings=_reglages_zeep())
    return client.create_service(liaison, adresse)


class _Camera:
    def __init__(
        self,
        session: requests.Session,
        hote: str,
        contact: Contact,
        identifiants: tuple[str, str] | None,
        flux: tuple[str, str],
        codec: str | None,
    ) -> None:
        self.session = session
        self.hote = hote
        self.contact = contact
        self.adresse = _adresse(contact, hote, CHEMIN_APPAREIL)
        self.identifiants = identifiants
        self._appareil: Any = None
        self._jeton: UsernameToken | None = None
        self._media: Any = None
        self._source = ""
        # Source vidéo de l'Image : celle du profil de la Caméra, lu par `lire` ; la première sans lui.
        self._source_video = ""
        # Chemin et requête de l'URL RTSP de la Caméra, et codec connu de son Flux.
        self.flux = flux
        self.codec = codec
        # Encodeur du profil de la Caméra, lu par `lire` : ce que `modifier` renvoie, champs changés.
        self._encodeur: _Encodeur | None = None

    def _connecter_appareil(self) -> None:
        """Service appareil, jeton daté à l'heure de la caméra : une fois par requête."""
        if self._appareil is not None:
            return
        appareil = _service(
            self.session, "devicemgmt", "{http://www.onvif.org/ver10/device/wsdl}DeviceBinding", self.adresse, None
        )
        jeton = None
        if self.identifiants is not None:
            decalage = _date_heure_utc(appareil.GetSystemDateAndTime()) - datetime.now(UTC)
            jeton = _JetonDecale(*self.identifiants, decalage=decalage)
        self._appareil = _service(
            self.session, "devicemgmt", "{http://www.onvif.org/ver10/device/wsdl}DeviceBinding", self.adresse, jeton
        )
        self._jeton = jeton

    def _connecter(self) -> None:
        """Services appareil et média, source vidéo : une fois par requête."""
        if self._media is not None:
            return
        self._connecter_appareil()
        # Seul le chemin de l'adresse annoncée sert : une caméra jointe en HTTPS l'annonce souvent en `http://…`
        # (ou sous un autre hôte, un autre port). Schéma, hôte et port restent ceux du contact retenu, pour
        # qu'aucune requête ne reparte en clair ni ailleurs.
        self._media = self._service_annonce(
            "media",
            "{http://www.onvif.org/ver10/media/wsdl}MediaBinding",
            self._appareil.GetCapabilities(Category="Media").Media.XAddr,
        )
        source = self._media.GetProfiles()[0].VideoSourceConfiguration
        self._source = source.token
        self._source_video = source.SourceToken

    def _service_annonce(self, wsdl: str, liaison: str, xaddr: str) -> Any:
        """Service à l'adresse annoncée `xaddr`, joint au contact retenu (seul son chemin sert)."""
        return _service(
            self.session, wsdl, liaison, _adresse(self.contact, self.hote, urlsplit(xaddr).path), self._jeton
        )

    def lire(self, maintenant: Callable[[], datetime]) -> Reglages:
        self._connecter()
        options = self._media.GetOSDOptions(ConfigurationToken=self._source).OSDOptions
        # L'Encodage avant l'Image : il retrouve le profil de la Caméra, dont la source vidéo porte l'Image.
        encodage = self._encodage()
        return Reglages(
            horloge=self._horloge(maintenant),
            incrustations=_incrustations(self._osds(), options),
            image=self._image(),
            encodage=encodage,
        )

    @cached_property
    def _service_media_2(self) -> Any:
        """Média 2 annoncé par `GetServices`, joint au contact retenu ; `None` sans média 2. Une fois par requête."""
        try:
            services = self._appareil.GetServices(IncludeCapability=False) or []
        except Fault as faute:
            if _identifiants_refuses(faute):
                raise
            # Caméra ancienne, sans `GetServices` : sans média 2.
            return None
        for service in services:
            if service.Namespace == ESPACE_MEDIA_2 and service.XAddr:
                return self._service_annonce(
                    "media2/media2", "{http://www.onvif.org/ver20/media/wsdl}Media2Binding", service.XAddr
                )
        return None

    def _encodage(self) -> Encodage:
        """Encodage du profil de l'URL RTSP ; réglable par le média 2, ou par le média 1 sur un Flux H.264."""
        self._encodeur = None
        try:
            media_2 = self._service_media_2
            encodeur = (
                _EncodeurMedia2.du_flux_par(media_2, self.flux)
                if media_2 is not None
                else _EncodeurMedia1.du_flux_par(self._media, self.flux)
            )
            if encodeur is None:
                return ENCODAGE_PROFIL_INTROUVABLE
            if encodeur.source_video:
                self._source_video = encodeur.source_video
            options = encodeur.options()
        except (Fault, TransportError) as erreur:
            if _identifiants_refuses(erreur):
                raise
            journal.info("ONVIF : Encodage non lu : %r", erreur)
            return ENCODAGE_NON_REGLABLE
        valeurs = encodeur.valeurs()
        # Le média 1 décrit mal le H.265 (ADR 0008) : le codec connu du Flux fait foi.
        if media_2 is None and self.codec:
            valeurs.codec = self.codec
        reglable = media_2 is not None or self.codec == "H264"
        if reglable:
            self._encodeur = encodeur
        return Encodage(
            reglable=reglable,
            raison=None if reglable else "non_reglable",
            profil=encodeur.profil,
            valeurs=valeurs,
            options=options,
        )

    @cached_property
    def _service_image(self) -> Any:
        """Service image annoncé, joint au contact retenu ; `None` sans service image. Une fois par requête."""
        annonce = self._appareil.GetCapabilities(Category="Imaging").Imaging
        if annonce is None or not annonce.XAddr:
            return None
        return self._service_annonce("imaging", "{http://www.onvif.org/ver20/imaging/wsdl}ImagingBinding", annonce.XAddr)

    def _image(self) -> Image:
        """Image de la source vidéo du profil ; non réglable sans service image ou s'il répond en faute."""
        try:
            service = self._service_image
            if service is None:
                return IMAGE_NON_REGLABLE
            options = _options_image(service.GetOptions(VideoSourceToken=self._source_video))
            reglages = service.GetImagingSettings(VideoSourceToken=self._source_video)
        except (Fault, TransportError) as erreur:
            if _identifiants_refuses(erreur):
                raise
            journal.info("ONVIF : Image non lue : %r", erreur)
            return IMAGE_NON_REGLABLE
        return Image(reglable=True, valeurs=_valeurs_image(reglages, options), options=options)

    def _horloge(self, maintenant: Callable[[], datetime]) -> Horloge:
        heure = self._appareil.GetSystemDateAndTime()
        date_heure_utc = _date_heure_utc(heure)
        ntp = self._appareil.GetNTP()
        fuseau_posix = heure.TimeZone.TZ if heure.TimeZone is not None else None
        return Horloge(
            date_heure_utc=date_heure_utc,
            ecart_s=(date_heure_utc - maintenant()).total_seconds(),
            fuseau_posix=fuseau_posix,
            fuseau=fuseaux.nom_lisible(fuseau_posix) if fuseau_posix else None,
            mode="ntp" if heure.DateTimeType == "NTP" else "manuel",
            serveur_ntp=_serveur_ntp(ntp),
        )

    def mettre_a_l_heure(self, maintenant: Callable[[], datetime]) -> Horloge:
        self._connecter()
        # Un refus se voit à l'écart relu, inchangé.
        self._regler_horloge(heure_du_site=maintenant())
        return self._horloge(maintenant)

    def lire_horloge(self, maintenant: Callable[[], datetime]) -> Horloge:
        self._connecter_appareil()
        return self._horloge(maintenant)

    def caler(self, serveur_ntp: str, fuseau_posix: str, maintenant: Callable[[], datetime]) -> Horloge:
        self._connecter_appareil()
        # Le serveur d'abord : la caméra passe en NTP déjà tournée vers le Site.
        self._appareil.SetNTP(FromDHCP=False, NTPManual=[_adresse_ntp(serveur_ntp)])
        heure = self._appareil.GetSystemDateAndTime()
        self._appareil.SetSystemDateAndTime(
            DateTimeType="NTP", DaylightSavings=bool(heure.DaylightSavings), TimeZone={"TZ": fuseau_posix}
        )
        return self._horloge(maintenant)

    def _regler_horloge(self, *, fuseau_posix: str | None = None, heure_du_site: datetime | None = None) -> bool:
        """`SetSystemDateAndTime` ; ce qui n'est pas demandé reste celui de la caméra. `False` : refusé.

        Sans `heure_du_site`, le mode est gardé et, en manuel, l'heure renvoyée est celle que la caméra vient de
        donner : ONVIF l'exige en mode manuel.
        """
        heure = self._appareil.GetSystemDateAndTime()
        manuel = heure_du_site is not None or heure.DateTimeType != "NTP"
        arguments: dict[str, Any] = {
            "DateTimeType": "Manual" if manuel else "NTP",
            "DaylightSavings": bool(heure.DaylightSavings),
        }
        fuseau = fuseau_posix or (heure.TimeZone.TZ if heure.TimeZone is not None else None)
        if fuseau:
            arguments["TimeZone"] = {"TZ": fuseau}
        if manuel:
            utc = (heure_du_site or _date_heure_utc(heure)).astimezone(UTC)
            arguments["UTCDateTime"] = {
                "Date": {"Year": utc.year, "Month": utc.month, "Day": utc.day},
                "Time": {"Hour": utc.hour, "Minute": utc.minute, "Second": utc.second},
            }
        return self._envoyer(self._appareil.SetSystemDateAndTime, **arguments)

    def modifier(self, modification: ModificationReglages, maintenant: Callable[[], datetime]) -> ResultatModification:
        lus = self.lire(maintenant)
        avant = lus.incrustations
        image = modification.image.model_dump(exclude_none=True)
        encodage = modification.encodage.model_dump(exclude_none=True)
        # Avant tout envoi : une valeur hors des options n'envoie rien, pas même les autres champs.
        _verifier_image(image, lus.image)
        _verifier_encodage(encodage, lus.encodage)
        fuseau = modification.horloge.fuseau
        fuseau_refuse = fuseau is not None and not self._regler_horloge(fuseau_posix=fuseaux.posix(fuseau))
        envois: list[tuple[CleIncrustation, dict[str, Any], set[str]]] = []
        for cle in TYPES_TEXTE:
            changement = getattr(modification.incrustations, cle)
            if changement is None:
                continue
            envoyes = changement.model_dump(exclude_none=True)
            if envoyes:
                envois.append((cle, envoyes, self._modifier_incrustation(cle, envoyes, getattr(avant, cle))))
        image_refusee = self._modifier_image(image, lus.image)
        # En dernier : il coupe le Flux, et la caméra peut se taire le temps de relancer son encodeur.
        encodage_refuse = bool(encodage) and not self._encodeur_du_flux.regler(encodage, self._envoyer)
        apres = self._relire_apres_encodage(maintenant) if encodage and not encodage_refuse else self.lire(maintenant)
        if apres is None:
            return ResultatModification(champs=_sans_reponse(modification), reglages=lus)
        champs = []
        if fuseau is not None:
            relu = apres.horloge.fuseau_posix
            statut = _statut(fuseau_refuse, relu, fuseaux.posix(fuseau))
            champs.append(ChampModifie(champ="horloge.fuseau", demande=fuseau, relu=relu, statut=statut))
        for cle, envoyes, refuses in envois:
            relue = getattr(apres.incrustations, cle)
            for champ, demande in envoyes.items():
                relu = getattr(relue, champ)
                statut = _statut(champ in refuses, relu, demande)
                champs.append(
                    ChampModifie(champ=f"incrustations.{cle}.{champ}", demande=demande, relu=relu, statut=statut)
                )
        valeurs_relues = apres.image.valeurs or ValeursImage()
        for champ, demande in image.items():
            relu = getattr(valeurs_relues, champ)
            statut = _statut(champ in image_refusee, relu, demande)
            champs.append(ChampModifie(champ=f"image.{champ}", demande=demande, relu=relu, statut=statut))
        encodage_relu = apres.encodage.valeurs
        for champ, demande in encodage.items():
            relu = getattr(encodage_relu, champ) if encodage_relu is not None else None
            statut = _statut(encodage_refuse, relu, demande)
            champs.append(ChampModifie(champ=f"encodage.{champ}", demande=demande, relu=relu, statut=statut))
        return ResultatModification(champs=champs, reglages=apres)

    @property
    def _encodeur_du_flux(self) -> "_Encodeur":
        # `_verifier_encodage` a refusé tout Encodage non réglable : l'encodeur a été lu.
        assert self._encodeur is not None
        return self._encodeur

    def _relire_apres_encodage(self, maintenant: Callable[[], datetime]) -> Reglages | None:
        """Relit la caméra jusqu'à ce qu'elle réponde, `DELAI_RELECTURE_S` au plus ; `None` : sans réponse."""
        echeance = time.monotonic() + DELAI_RELECTURE_S
        while True:
            try:
                return self.lire(maintenant)
            except (requests.ConnectionError, requests.Timeout, TransportError) as erreur:
                if _identifiants_refuses(erreur):
                    raise
                journal.info("ONVIF : caméra pas encore revenue après l'Encodage : %r", erreur)
            reste = echeance - time.monotonic()
            if reste <= 0:
                return None
            # Dernière tentative à l'échéance.
            time.sleep(min(PAS_RELECTURE_S, reste))

    def _modifier_image(self, image: dict[str, Any], lue: Image) -> set[str]:
        """Un `SetImagingSettings` par paramètre (le niveau avec son mode) ; rend les champs refusés."""
        if not image:
            return set()
        service = self._service_image
        refuses: set[str] = set()
        envois: list[tuple[set[str], dict[str, Any]]] = []
        if "infrarouge" in image:
            envois.append(({"infrarouge"}, {"IrCutFilter": image["infrarouge"]}))
        for champ, element in PARAMETRES_IMAGE.items():
            if champ in image:
                envois.append(({champ}, {element: image[champ]}))
        valeurs = lue.valeurs or ValeursImage()
        for champ, element in COMPENSATIONS_IMAGE.items():
            niveau = f"{champ}_niveau"
            envoyes = {champ, niveau} & set(image)
            if not envoyes:
                continue
            # Le mode est exigé par ONVIF : celui relu quand seul le niveau change.
            compensation: dict[str, Any] = {"Mode": image.get(champ, getattr(valeurs, champ))}
            if niveau in image:
                compensation["Level"] = image[niveau]
            envois.append((envoyes, {element: compensation}))
        for champs_envoyes, reglages in envois:
            if not self._envoyer(
                service.SetImagingSettings, VideoSourceToken=self._source_video, ImagingSettings=reglages
            ):
                refuses |= champs_envoyes
        return refuses

    def _modifier_incrustation(
        self, cle: CleIncrustation, envoyes: dict[str, Any], lue: IncrustationNom | IncrustationDateHeure
    ) -> set[str]:
        """Envoie les champs d'une Incrustation ; rend ceux qui ont été refusés."""
        if envoyes.get("affichee") is False:
            return self._cacher_incrustation(TYPES_TEXTE[cle])
        if not lue.affichee:
            return self._reafficher_incrustation(cle, envoyes, lue.peut_etre_reaffichee)
        return self._changer_incrustation(TYPES_TEXTE[cle], envoyes)

    def _cacher_incrustation(self, type_texte: str) -> set[str]:
        osd = self._osd(type_texte)
        return set() if osd is None or self._envoyer(self._media.DeleteOSD, OSDToken=osd.token) else {"affichee"}

    def _reafficher_incrustation(
        self, cle: CleIncrustation, envoyes: dict[str, Any], peut_etre_reaffichee: bool
    ) -> set[str]:
        # Seule une création la fait revenir, avec son texte et son coin : sans annonce, rien n'est envoyé.
        if envoyes.get("affichee") is not True or not peut_etre_reaffichee:
            return set(envoyes)
        type_texte = TYPES_TEXTE[cle]
        texte = {"PlainText": envoyes.get("texte", "")} if type_texte == "Plain" else {}
        osd = {
            "token": "",
            "VideoSourceConfigurationToken": self._source,
            "Type": "Text",
            "Position": {"Type": envoyes.get("position", COINS_PAR_DEFAUT[cle])},
            "TextString": {"Type": type_texte, **texte},
        }
        return set() if self._envoyer(self._media.CreateOSD, OSD=osd) else set(envoyes)

    def _changer_incrustation(self, type_texte: str, envoyes: dict[str, Any]) -> set[str]:
        refuses = set()
        # Un `SetOSD` par champ, sur l'Incrustation relue à chaque fois : un refus ne fausse pas le suivant.
        for champ in ("texte", "position"):
            if champ not in envoyes:
                continue
            osd = self._osd(type_texte)
            if osd is None:
                refuses.add(champ)
                continue
            if champ == "texte":
                osd.TextString.PlainText = envoyes["texte"]
            else:
                # Un coin remplace une position personnalisée et ses coordonnées.
                osd.Position.Type = envoyes["position"]
                osd.Position.Pos = None
            if not self._envoyer(self._media.SetOSD, OSD=osd):
                refuses.add(champ)
        return refuses

    def _envoyer(self, operation: Callable[..., Any], **arguments: Any) -> bool:
        """`False` si la caméra refuse (faute SOAP autre qu'un refus d'identifiants)."""
        try:
            operation(**arguments)
        except Fault as faute:
            if _identifiants_refuses(faute):
                raise
            journal.info("ONVIF : réglage refusé par la caméra : %s", faute.message)
            return False
        return True

    def _osds(self) -> list[Any]:
        return self._media.GetOSDs(ConfigurationToken=self._source) or []

    def _osd(self, type_texte: str) -> Any:
        return _textes(self._osds()).get(type_texte)


def _statut(refuse: bool, relu: object, demande: object) -> StatutChamp:
    """`refuse` si la caméra a refusé l'envoi ; sinon `pris` si la valeur relue est celle demandée."""
    if refuse:
        return "refuse"
    return "pris" if relu == demande else "pas_pris"


def _sans_reponse(modification: ModificationReglages) -> list[ChampModifie]:
    """Chaque champ envoyé, `pas_pris` faute d'avoir pu relire la caméra."""
    envoyes: list[tuple[str, Any]] = []
    if modification.horloge.fuseau is not None:
        envoyes.append(("horloge.fuseau", modification.horloge.fuseau))
    for cle in TYPES_TEXTE:
        changement = getattr(modification.incrustations, cle)
        if changement is not None:
            envoyes += [(f"incrustations.{cle}.{c}", v) for c, v in changement.model_dump(exclude_none=True).items()]
    for section in ("image", "encodage"):
        valeurs = getattr(modification, section).model_dump(exclude_none=True)
        envoyes += [(f"{section}.{champ}", demande) for champ, demande in valeurs.items()]
    return [
        ChampModifie(champ=champ, demande=demande, relu=None, statut="pas_pris", raison="sans_reponse")
        for champ, demande in envoyes
    ]


def _verifier_encodage(encodage: dict[str, Any], lu: Encodage) -> None:
    """Lève `HorsDesOptions` pour tout Encodage non réglable, ou le premier champ hors des options relues."""
    if not encodage:
        return
    if not lu.reglable or lu.options is None:
        raise HorsDesOptions("encodage")
    for champ, demande in encodage.items():
        proposees = lu.options.resolutions if champ == "resolution" else getattr(lu.options, champ)
        if not _proposee(demande, proposees):
            raise HorsDesOptions(f"encodage.{champ}")


def _verifier_image(image: dict[str, Any], lue: Image) -> None:
    """Lève `HorsDesOptions` pour le premier champ que la caméra ne propose pas, ou hors de ses bornes."""
    options = lue.options or OptionsImage()
    for champ, demande in image.items():
        if not _proposee(demande, getattr(options, champ)):
            raise HorsDesOptions(f"image.{champ}")


def _proposee(demande: Any, proposees: Bornes | list[Any] | None) -> bool:
    """`demande` dans les bornes, ou parmi les valeurs, que la caméra propose ; `False` si elle ne propose rien."""
    if proposees is None:
        return False
    return proposees.contient(demande) if isinstance(proposees, Bornes) else demande in proposees


def _bornes(plage: Any) -> Bornes | None:
    if plage is None or plage.Min is None or plage.Max is None:
        return None
    return Bornes(min=plage.Min, max=plage.Max)


def _modes[M](modes: Any, connus: tuple[M, ...]) -> list[M] | None:
    """Modes annoncés qu'ArgOS connaît, dans l'ordre de la caméra ; `None` si aucun."""
    retenus = [mode for mode in (modes or []) if mode in connus]
    return retenus or None


def _options_image(options: Any) -> OptionsImage:
    """`GetOptions` du service image : seulement ce que la caméra annonce."""
    proposees: dict[str, Any] = {
        "infrarouge": _modes(options.IrCutFilterModes, ("ON", "OFF", "AUTO")),
        **{champ: _bornes(getattr(options, element, None)) for champ, element in PARAMETRES_IMAGE.items()},
    }
    for champ, element in COMPENSATIONS_IMAGE.items():
        compensation = getattr(options, element, None)
        modes = _modes(compensation.Mode, ("OFF", "ON")) if compensation is not None else None
        proposees[champ] = modes
        # Un niveau sans mode n'aurait rien à régler.
        proposees[f"{champ}_niveau"] = _bornes(compensation.Level) if compensation is not None and modes else None
    return OptionsImage(**proposees)


def _valeurs_image(reglages: Any, options: OptionsImage) -> ValeursImage:
    """`GetImagingSettings` : seulement les paramètres proposés par `options`."""
    lues: dict[str, Any] = {
        "infrarouge": reglages.IrCutFilter,
        **{champ: getattr(reglages, element, None) for champ, element in PARAMETRES_IMAGE.items()},
    }
    for champ, element in COMPENSATIONS_IMAGE.items():
        compensation = getattr(reglages, element, None)
        lues[champ] = compensation.Mode if compensation is not None else None
        lues[f"{champ}_niveau"] = compensation.Level if compensation is not None else None
    proposees = options.model_dump()
    return ValeursImage(**{champ: valeur for champ, valeur in lues.items() if proposees[champ] is not None})


def _date_heure_utc(heure: Any) -> datetime:
    utc = heure.UTCDateTime
    return datetime(
        utc.Date.Year, utc.Date.Month, utc.Date.Day, utc.Time.Hour, utc.Time.Minute, utc.Time.Second, tzinfo=UTC
    )


def _adresse_ntp(serveur: str) -> dict[str, str]:
    """Serveur NTP manuel d'ONVIF : une IPv4 en `IPv4`, un nom en `DNS`."""
    try:
        return {"Type": "IPv4", "IPv4Address": str(IPv4Address(serveur))}
    except ValueError:
        return {"Type": "DNS", "DNSname": serveur}


def _serveur_ntp(ntp: Any) -> str | None:
    serveurs = (ntp.NTPFromDHCP if ntp.FromDHCP else ntp.NTPManual) or []
    for serveur in serveurs:
        nom = {"DNS": serveur.DNSname, "IPv4": serveur.IPv4Address, "IPv6": serveur.IPv6Address}.get(serveur.Type)
        if nom:
            return nom
    return None


def _textes(osds: list[Any]) -> dict[str, Any]:
    """Première Incrustation de texte de chaque type : `Plain` (le nom), `DateAndTime` (la date et heure)."""
    textes: dict[str, Any] = {}
    for osd in osds:
        if osd.TextString is None:
            continue
        type_texte = "DateAndTime" if osd.TextString.Type in ("DateAndTime", "Date", "Time") else osd.TextString.Type
        textes.setdefault(type_texte, osd)
    return textes


def _incrustations(osds: list[Any], options: Any) -> Incrustations:
    textes = _textes(osds)
    nom, date_heure = textes.get("Plain"), textes.get("DateAndTime")
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


# --- Encodage : médias 1 et 2 -----------------------------------------------------------------------------------


def _texte_resolution(resolution: Any) -> str:
    return f"{resolution.Width}x{resolution.Height}"


def _resolution(texte: str) -> dict[str, int]:
    largeur, hauteur = texte.split("x")
    return {"Width": int(largeur), "Height": int(hauteur)}


class _Encodeur:
    """Configuration d'encodeur du profil d'un Flux, lue par l'un des médias, et ce qu'elle propose."""

    def __init__(self, service: Any, profil: Any, configuration: Any, source_video: str | None) -> None:
        self.service = service
        self.token_profil = profil.token
        self.profil: str = profil.Name or profil.token
        self.configuration = configuration
        # Source vidéo du profil (`SourceToken`) ; `None` s'il n'en dit rien.
        self.source_video = source_video

    def valeurs(self) -> ValeursEncodage:
        configuration = self.configuration
        controle = configuration.RateControl
        return ValeursEncodage(
            resolution=_texte_resolution(configuration.Resolution),
            images_par_seconde=controle.FrameRateLimit if controle is not None else None,
            debit_max=controle.BitrateLimit if controle is not None else None,
            codec=configuration.Encoding,
            qualite=configuration.Quality,
            intervalle_images_cles=self._intervalle_images_cles(),
        )

    def regler(self, encodage: dict[str, Any], envoyer: Callable[..., bool]) -> bool:
        """Envoie la configuration relue, seuls les champs d'`encodage` changés ; `False` : refusée."""
        configuration = self.configuration
        if "resolution" in encodage:
            configuration.Resolution = _resolution(encodage["resolution"])
        if "images_par_seconde" in encodage:
            configuration.RateControl.FrameRateLimit = encodage["images_par_seconde"]
        if "debit_max" in encodage:
            configuration.RateControl.BitrateLimit = encodage["debit_max"]
        return self._envoyer(envoyer)

    def options(self) -> OptionsEncodage:
        raise NotImplementedError

    def _intervalle_images_cles(self) -> int | None:
        raise NotImplementedError

    def _envoyer(self, envoyer: Callable[..., bool]) -> bool:
        raise NotImplementedError


class _EncodeurMedia1(_Encodeur):
    """Média 1 (`ver10/media`) : options par codec, débit dans l'extension."""

    @staticmethod
    def du_flux_par(media: Any, flux: tuple[str, str]) -> "_EncodeurMedia1 | None":
        for profil in media.GetProfiles():
            if profil.VideoEncoderConfiguration is None:
                continue
            uri = media.GetStreamUri(
                StreamSetup={"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}, ProfileToken=profil.token
            ).Uri
            if _flux(uri) == flux:
                source = profil.VideoSourceConfiguration
                return _EncodeurMedia1(
                    media, profil, profil.VideoEncoderConfiguration, source.SourceToken if source else None
                )
        return None

    def options(self) -> OptionsEncodage:
        options = self.service.GetVideoEncoderConfigurationOptions(
            ConfigurationToken=self.configuration.token, ProfileToken=self.token_profil
        )
        codec = self.configuration.Encoding
        par_codec = getattr(options, codec, None) if codec in ("H264", "MPEG4", "JPEG") else None
        return OptionsEncodage(
            resolutions=[_texte_resolution(r) for r in (par_codec.ResolutionsAvailable if par_codec else [])],
            images_par_seconde=_bornes(par_codec.FrameRateRange) if par_codec else None,
            debit_max=_debit_de_l_extension(options.Extension, codec),
        )

    def _intervalle_images_cles(self) -> int | None:
        h264 = self.configuration.H264
        return h264.GovLength if h264 is not None else None

    def _envoyer(self, envoyer: Callable[..., bool]) -> bool:
        return envoyer(
            self.service.SetVideoEncoderConfiguration, Configuration=self.configuration, ForcePersistence=True
        )


def _debit_de_l_extension(extension: Any, codec: str) -> Bornes | None:
    """Bornes du débit, dans l'extension des options du média 1 (`BitrateRange` du codec) ; `None` sans elles.

    Le schéma ouvre l'extension par un `xs:any` : zeep y range souvent l'élément du codec, brut, plutôt que typé.
    """
    if extension is None:
        return None
    if (options_codec := getattr(extension, codec, None)) is not None:
        return _bornes(options_codec.BitrateRange)
    for brut in getattr(extension, "_value_1", None) or []:
        if getattr(brut, "tag", None) != f"{{{ESPACE_SCHEMA}}}{codec}":
            continue
        minimum = brut.findtext(f"{{{ESPACE_SCHEMA}}}BitrateRange/{{{ESPACE_SCHEMA}}}Min")
        maximum = brut.findtext(f"{{{ESPACE_SCHEMA}}}BitrateRange/{{{ESPACE_SCHEMA}}}Max")
        if minimum is not None and maximum is not None:
            return Bornes(min=float(minimum), max=float(maximum))
    return None


class _EncodeurMedia2(_Encodeur):
    """Média 2 (`ver20/media`) : décrit le vrai codec (H.265 compris), options par codec."""

    @staticmethod
    def du_flux_par(media_2: Any, flux: tuple[str, str]) -> "_EncodeurMedia2 | None":
        for profil in media_2.GetProfiles(Type=["VideoSource", "VideoEncoder"]):
            configurations = profil.Configurations
            if configurations is None or configurations.VideoEncoder is None:
                continue
            if _flux(media_2.GetStreamUri(Protocol="RTSP", ProfileToken=profil.token)) == flux:
                source = configurations.VideoSource
                return _EncodeurMedia2(
                    media_2, profil, configurations.VideoEncoder, source.SourceToken if source else None
                )
        return None

    def options(self) -> OptionsEncodage:
        proposees = self.service.GetVideoEncoderConfigurationOptions(ConfigurationToken=self.configuration.token) or []
        # Une entrée par codec : celle du codec du Flux, qui ne change pas.
        options = next((o for o in proposees if o.Encoding == self.configuration.Encoding), None)
        if options is None:
            return OptionsEncodage(resolutions=[])
        images = [float(i) for i in (options.FrameRatesSupported or [])]
        return OptionsEncodage(
            resolutions=[_texte_resolution(r) for r in options.ResolutionsAvailable or []],
            images_par_seconde=Bornes(min=min(images), max=max(images)) if images else None,
            debit_max=_bornes(options.BitrateRange),
        )

    def _intervalle_images_cles(self) -> int | None:
        return self.configuration.GovLength

    def _envoyer(self, envoyer: Callable[..., bool]) -> bool:
        return envoyer(self.service.SetVideoEncoderConfiguration, Configuration=self.configuration)


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
