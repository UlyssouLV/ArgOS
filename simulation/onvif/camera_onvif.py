"""Caméra simulée ONVIF : service SOAP 1.2 en bibliothèque standard, état en mémoire, « sortie d'usine » au démarrage.

Seulement les opérations dont ArgOS se sert pour les Réglages de la Caméra (README.md). Lancé dans le réseau
d'une Caméra simulée (compose.simulation.yaml), il lui donne une interface ONVIF : même IP, même MAC.

Configuration par variables d'environnement : `ONVIF_PORT` (HTTP) et `ONVIF_PORT_HTTPS` (HTTPS), l'un, l'autre
ou les deux (HTTP sur 80 si aucun) ; en HTTPS, `ONVIF_CERTIFICAT` et `ONVIF_CLE` (chemins du certificat et de sa clé,
créés auto-signés s'ils n'existent pas) ; `ONVIF_IDENTIFIANT` et `ONVIF_MOT_DE_PASSE` (WS-Security exigé seulement
s'ils sont tous deux renseignés), `ONVIF_TYPES_CREABLES` (types d'Incrustation que la caméra sait recréer, séparés
par des virgules ; les deux par défaut), `ONVIF_TLS_MAX` (version TLS la plus haute servie, `1.0` à `1.3` : une
caméra ancienne), `ONVIF_SERVICES` (services en plus de l'appareil et du média 1, séparés par des virgules : `image`,
`media2` ; aucun par défaut), `ONVIF_CHEMINS_RTSP` (chemin et requête de l'URL RTSP de chaque profil, séparés par des
virgules : un ou deux profils ; `/Streaming/Channels/101` par défaut), `ONVIF_SILENCE_APRES_ENCODAGE_S` (secondes
pendant lesquelles la caméra ferme chaque connexion sans répondre après un changement d'Encodage accepté, comme une
caméra qui relance son encodeur ; jamais par défaut). HTTP et HTTPS servent la même caméra (même
état). Chaque requête est journalisée avec son schéma et son port (`https:443`, `http:8899`), puis le nom de son
opération SOAP : les tests y lisent ce que la caméra a reçu, et par où.
`python camera_onvif.py sonde` lit l'heure du service local sur chaque port : healthcheck du conteneur.
"""

import base64
import hashlib
import hmac
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape, quoteattr

CHEMIN_APPAREIL = "/onvif/device_service"
CHEMIN_MEDIA = "/onvif/media_service"
CHEMIN_IMAGE = "/onvif/imaging_service"
CHEMIN_MEDIA_2 = "/onvif/media2_service"
OPENSSL = "/usr/bin/openssl"

# Espaces de noms XML : des noms imposés par SOAP et ONVIF, jamais appelés (NOSONAR définitif).
ENV = "http://www.w3.org/2003/05/soap-envelope"  # NOSONAR
TDS = "http://www.onvif.org/ver10/device/wsdl"  # NOSONAR
TRT = "http://www.onvif.org/ver10/media/wsdl"  # NOSONAR
TT = "http://www.onvif.org/ver10/schema"  # NOSONAR
TIMG = "http://www.onvif.org/ver20/imaging/wsdl"  # NOSONAR
TR2 = "http://www.onvif.org/ver20/media/wsdl"  # NOSONAR
TER = "http://www.onvif.org/ver10/error"  # NOSONAR
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"  # NOSONAR
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"  # NOSONAR
NS = {"env": ENV, "tds": TDS, "trt": TRT, "timg": TIMG, "tr2": TR2, "tt": TT, "wsse": WSSE, "wsu": WSU}

# Seule opération lue sans identifiants, comme sur les vraies caméras : le client y lit l'heure de la caméra.
SANS_IDENTIFIANTS = {"GetSystemDateAndTime"}

SOURCE_VIDEO = "VideoSource_1"
CONFIGURATION_SOURCE = "VideoSourceConfig_1"
POSITIONS = ("UpperLeft", "UpperRight", "LowerLeft", "LowerRight", "Custom")
FORMATS_DATE = ("yyyy-MM-dd", "MM/dd/yyyy", "dd/MM/yyyy")
FORMATS_HEURE = ("HH:mm:ss", "hh:mm:ss tt")
TYPES_TEXTE = ("Plain", "DateAndTime")
# Texte incrusté le plus long accepté : au-delà, faute, comme beaucoup de caméras.
LONGUEUR_MAX_TEXTE = 32

# Services en plus de l'appareil et du média 1 (`ONVIF_SERVICES`).
SERVICES = ("image", "media2")
CHEMINS_RTSP = ("/Streaming/Channels/101",)

# Image : bornes des paramètres réglables (`GetOptions`), modes du filtre infrarouge, du contre-jour et du WDR.
# Le contre-jour n'annonce pas de bornes de niveau : un niveau non proposé, mode seul.
BORNES_IMAGE = (0, 100)
MODES_INFRAROUGE = ("ON", "OFF", "AUTO")
MODES_CONTRE_JOUR = ("OFF", "ON")
MODES_WDR = ("OFF", "ON")
# Paramètres d'image bornés : élément ONVIF → attribut de `Image`.
PARAMETRES_IMAGE = {
    "Brightness": "luminosite",
    "ColorSaturation": "saturation",
    "Contrast": "contraste",
    "Sharpness": "nettete",
}

# Encodage : bornes des images par seconde et de la qualité, plage du GOP.
IMAGES_PAR_SECONDE = (1, 22)
QUALITE = (1, 6)
GOP = (1, 100)


class Faute(Exception):
    """Faute SOAP renvoyée au client : sous-code ONVIF (`ter:…`) et code SOAP (`env:Sender` ou `env:Receiver`)."""

    def __init__(self, sous_code: str, raison: str, code: str = "env:Sender") -> None:
        super().__init__(raison)
        self.sous_code, self.raison, self.code = sous_code, raison, code


@dataclass
class Incrustation:
    token: str
    type_texte: str
    position: str
    texte: str = ""
    format_date: str = ""
    format_heure: str = ""
    # Position personnalisée : coordonnées normalisées (-1 à 1), gardées telles quelles.
    x: str = ""
    y: str = ""


@dataclass
class Image:
    """Image « usine » : le WDR est retenu tel quel, jamais changé (la caméra l'accepte sans l'appliquer)."""

    infrarouge: str = "AUTO"
    luminosite: float = 50
    saturation: float = 50
    contraste: float = 50
    nettete: float = 50
    contre_jour: str = "OFF"
    wdr: str = "OFF"
    wdr_niveau: float = 50


@dataclass
class Encodeur:
    """Configuration d'encodeur d'un profil, partagée par les médias 1 et 2. Le codec ne change jamais."""

    token: str
    resolutions: tuple[tuple[int, int], ...]
    debits: tuple[int, int]
    resolution: tuple[int, int]
    images_par_seconde: float
    debit: int
    gop: int
    qualite: float = 4
    codec: str = "H264"


def _encodeurs_d_usine() -> list[Encodeur]:
    """Flux principal et secondaire de la caméra de dev ; la vidéo simulée, elle, ne change pas."""
    return [
        Encodeur(
            "VideoEncoderConfig_1",
            resolutions=((2304, 1296), (1920, 1080), (1280, 720)),
            debits=(512, 8192),
            resolution=(2304, 1296),
            images_par_seconde=20,
            debit=4096,
            gop=40,
        ),
        Encodeur(
            "VideoEncoderConfig_2",
            resolutions=((800, 448), (640, 360), (352, 288)),
            debits=(64, 2048),
            resolution=(800, 448),
            images_par_seconde=15,
            debit=512,
            gop=30,
        ),
    ]


@dataclass
class Etat:
    """État « sortie d'usine » d'une caméra de dev XiongMai, en mémoire seulement."""

    # Horloge : écart entre l'heure de la caméra et l'heure réelle, pour qu'elle avance.
    decalage: timedelta = field(default_factory=lambda: datetime(1999, 12, 31, tzinfo=UTC) - datetime.now(UTC))
    mode: str = "Manual"
    heure_ete: bool = False
    fuseau: str = "AWST-8"
    serveur_ntp: str = "NTP"
    incrustations: list[Incrustation] = field(
        default_factory=lambda: [
            Incrustation("OSD_1", "Plain", "UpperLeft", texte="CAM01"),
            Incrustation("OSD_2", "DateAndTime", "LowerLeft", format_date="yyyy-MM-dd", format_heure="HH:mm:ss"),
        ]
    )
    prochain_token: int = 3
    image: Image = field(default_factory=Image)
    encodeurs: list[Encodeur] = field(default_factory=_encodeurs_d_usine)
    verrou: threading.Lock = field(default_factory=threading.Lock)

    def heure(self) -> datetime:
        return datetime.now(UTC) + self.decalage


# --- Lecture des requêtes ---------------------------------------------------------------------------------------


def _texte(element: ET.Element, chemin: str, defaut: str = "") -> str:
    trouve = element.find(chemin, NS)
    return (trouve.text or "").strip() if trouve is not None else defaut


def _exiger(element: ET.Element, chemin: str) -> str:
    valeur = _texte(element, chemin)
    if not valeur:
        raise Faute("ter:InvalidArgVal", f"{chemin} manquant")
    return valeur


def _verifier_identifiants(entete: ET.Element | None, identifiants: tuple[str, str]) -> None:
    """WS-Security UsernameToken, mot de passe en empreinte : Base64(SHA1(nonce + created + mot de passe))."""
    jeton = entete.find("wsse:Security/wsse:UsernameToken", NS) if entete is not None else None
    if jeton is None:
        raise Faute("ter:NotAuthorized", "Identifiants exigés")
    identifiant, mot_de_passe = identifiants
    try:
        nonce = base64.b64decode(_texte(jeton, "wsse:Nonce"), validate=True)
    except ValueError:
        raise Faute("ter:NotAuthorized", "Nonce illisible") from None
    attendue = base64.b64encode(
        hashlib.sha1(nonce + _texte(jeton, "wsu:Created").encode() + mot_de_passe.encode()).digest()  # NOSONAR : SHA-1 imposé par WS-Security
    ).decode()
    bon_identifiant = hmac.compare_digest(_texte(jeton, "wsse:Username"), identifiant)
    bonne_empreinte = hmac.compare_digest(_texte(jeton, "wsse:Password"), attendue)
    if not (bon_identifiant and bonne_empreinte):
        raise Faute("ter:NotAuthorized", "Identifiants refusés")


def _nombre(element: ET.Element, chemin: str, bornes: tuple[float, float], sous_code: str) -> float | None:
    """Nombre lu à `chemin`, None s'il est absent ; faute `sous_code` s'il est illisible ou hors des `bornes`."""
    texte = _texte(element, chemin)
    if not texte:
        return None
    try:
        valeur = float(texte)
    except ValueError:
        raise Faute(sous_code, f"{chemin} illisible : {texte}") from None
    if not bornes[0] <= valeur <= bornes[1]:
        raise Faute(sous_code, f"{chemin} hors des bornes {bornes[0]:g} à {bornes[1]:g} : {texte}")
    return valeur


def _mode(element: ET.Element, chemin: str, modes: tuple[str, ...]) -> str | None:
    mode = _texte(element, chemin)
    if mode and mode not in modes:
        raise Faute("ter:InvalidArgVal", f"{chemin} inconnu : {mode}")
    return mode or None


def _lire_incrustation(osd: ET.Element, token: str) -> Incrustation:
    type_texte = _exiger(osd, "tt:TextString/tt:Type")
    position = _exiger(osd, "tt:Position/tt:Type")
    if type_texte not in TYPES_TEXTE:
        raise Faute("ter:InvalidArgVal", f"Type de texte non pris en charge : {type_texte}")
    if position not in POSITIONS:
        raise Faute("ter:InvalidArgVal", f"Position inconnue : {position}")
    if len(_texte(osd, "tt:TextString/tt:PlainText")) > LONGUEUR_MAX_TEXTE:
        raise Faute("ter:InvalidArgVal", f"Texte de plus de {LONGUEUR_MAX_TEXTE} caractères")
    pos = osd.find("tt:Position/tt:Pos", NS)
    return Incrustation(
        token,
        type_texte,
        position,
        texte=_texte(osd, "tt:TextString/tt:PlainText"),
        format_date=_texte(osd, "tt:TextString/tt:DateFormat"),
        format_heure=_texte(osd, "tt:TextString/tt:TimeFormat"),
        x=pos.get("x", "") if pos is not None else "",
        y=pos.get("y", "") if pos is not None else "",
    )


# --- Écriture des réponses --------------------------------------------------------------------------------------


def _date_heure(moment: datetime) -> str:
    # tt:DateTime : l'heure avant la date (ordre du schéma, exigé par les clients stricts).
    return (
        f"<tt:Time><tt:Hour>{moment.hour}</tt:Hour><tt:Minute>{moment.minute}</tt:Minute>"
        f"<tt:Second>{moment.second}</tt:Second></tt:Time>"
        f"<tt:Date><tt:Year>{moment.year}</tt:Year><tt:Month>{moment.month}</tt:Month><tt:Day>{moment.day}</tt:Day></tt:Date>"
    )


def _incrustation_xml(osd: Incrustation, balise: str) -> str:
    pos = f"<tt:Pos x={quoteattr(osd.x)} y={quoteattr(osd.y)}/>" if osd.position == "Custom" and osd.x else ""
    if osd.type_texte == "Plain":
        texte = f"<tt:PlainText>{escape(osd.texte)}</tt:PlainText>"
    else:
        texte = f"<tt:DateFormat>{escape(osd.format_date)}</tt:DateFormat><tt:TimeFormat>{escape(osd.format_heure)}</tt:TimeFormat>"
    return (
        f"<{balise} token={quoteattr(osd.token)}>"
        f"<tt:VideoSourceConfigurationToken>{CONFIGURATION_SOURCE}</tt:VideoSourceConfigurationToken>"
        f"<tt:Type>Text</tt:Type><tt:Position><tt:Type>{osd.position}</tt:Type>{pos}</tt:Position>"
        f"<tt:TextString><tt:Type>{osd.type_texte}</tt:Type>{texte}</tt:TextString>"
        f"</{balise}>"
    )


def _bornes(balise: str, bornes: tuple[float, float]) -> str:
    return f"<{balise}><tt:Min>{bornes[0]:g}</tt:Min><tt:Max>{bornes[1]:g}</tt:Max></{balise}>"


def _source_video_xml(balise: str) -> str:
    return (
        f'<{balise} token="{CONFIGURATION_SOURCE}"><tt:Name>VideoSourceConfig</tt:Name>'
        f"<tt:UseCount>1</tt:UseCount><tt:SourceToken>{SOURCE_VIDEO}</tt:SourceToken>"
        f'<tt:Bounds x="0" y="0" width="1280" height="720"/></{balise}>'
    )


def _resolution(resolution: tuple[int, int], balise: str = "tt:Resolution") -> str:
    return f"<{balise}><tt:Width>{resolution[0]}</tt:Width><tt:Height>{resolution[1]}</tt:Height></{balise}>"


def _encodeur_xml(encodeur: Encodeur, balise: str) -> str:
    """Configuration d'encodeur du média 1. Il ne sait décrire que le H.264 : comme la caméra de dev, il l'annonce."""
    return (
        f"<{balise} token={quoteattr(encodeur.token)}><tt:Name>{encodeur.token}</tt:Name><tt:UseCount>1</tt:UseCount>"
        f"<tt:Encoding>H264</tt:Encoding>{_resolution(encodeur.resolution)}<tt:Quality>{encodeur.qualite:g}</tt:Quality>"
        f"<tt:RateControl><tt:FrameRateLimit>{encodeur.images_par_seconde:g}</tt:FrameRateLimit>"
        f"<tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>{encodeur.debit}</tt:BitrateLimit></tt:RateControl>"
        f"<tt:H264><tt:GovLength>{encodeur.gop}</tt:GovLength><tt:H264Profile>Main</tt:H264Profile></tt:H264>"
        "<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address>"
        "<tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>"
        f"<tt:SessionTimeout>PT60S</tt:SessionTimeout></{balise}>"
    )


def _encodeur_2_xml(encodeur: Encodeur, balise: str) -> str:
    """Configuration d'encodeur du média 2, qui décrit le vrai codec."""
    return (
        f"<{balise} token={quoteattr(encodeur.token)} GovLength=\"{encodeur.gop}\" Profile=\"Main\">"
        f"<tt:Name>{encodeur.token}</tt:Name><tt:UseCount>1</tt:UseCount><tt:Encoding>{encodeur.codec}</tt:Encoding>"
        f'{_resolution(encodeur.resolution)}<tt:RateControl ConstantBitRate="false">'
        f"<tt:FrameRateLimit>{encodeur.images_par_seconde:g}</tt:FrameRateLimit>"
        f"<tt:BitrateLimit>{encodeur.debit}</tt:BitrateLimit></tt:RateControl>"
        f"<tt:Quality>{encodeur.qualite:g}</tt:Quality></{balise}>"
    )


def _enveloppe(corps: str) -> str:
    declarations = " ".join(f'xmlns:{prefixe}="{uri}"' for prefixe, uri in NS.items() if prefixe not in ("wsse", "wsu"))
    return f'<?xml version="1.0" encoding="UTF-8"?><env:Envelope {declarations} xmlns:ter="{TER}"><env:Body>{corps}</env:Body></env:Envelope>'


def _faute_xml(faute: Faute) -> str:
    return _enveloppe(
        f"<env:Fault><env:Code><env:Value>{faute.code}</env:Value>"
        f"<env:Subcode><env:Value>{faute.sous_code}</env:Value></env:Subcode></env:Code>"
        f'<env:Reason><env:Text xml:lang="en">{escape(faute.raison)}</env:Text></env:Reason></env:Fault>'
    )


# --- Opérations -------------------------------------------------------------------------------------------------


@dataclass
class Profil:
    token: str
    nom: str
    chemin_rtsp: str
    encodeur: Encodeur


class Camera:
    def __init__(
        self,
        identifiants: tuple[str, str] | None = None,
        types_creables: tuple[str, ...] = TYPES_TEXTE,
        services: frozenset[str] = frozenset(),
        chemins_rtsp: tuple[str, ...] = CHEMINS_RTSP,
        silence_apres_encodage_s: float = 0,
    ) -> None:
        """`services` : `image` et `media2` en plus de l'appareil et du média 1 ; `chemins_rtsp` : un profil par chemin ;
        `silence_apres_encodage_s` : muette ce temps-là après chaque changement d'Encodage accepté."""
        self.identifiants = identifiants
        self.silence_apres_encodage_s = silence_apres_encodage_s
        # Instant (`time.monotonic`) jusqu'auquel la caméra ne répond plus.
        self.muette_jusqu_a = 0.0
        self.types_creables = types_creables
        self.etat = Etat()
        if not 1 <= len(chemins_rtsp) <= len(self.etat.encodeurs):
            raise ValueError(f"Un ou {len(self.etat.encodeurs)} profils, pas {len(chemins_rtsp)}")
        self.profils = [
            Profil(f"Profile_{numero}", nom, chemin, encodeur)
            for numero, (nom, chemin, encodeur) in enumerate(
                zip(("mainStream", "subStream"), chemins_rtsp, self.etat.encodeurs), start=1
            )
        ]
        # Services annoncés par GetServices : espace de noms, chemin, version.
        self.services = [(TDS, CHEMIN_APPAREIL, (2, 60)), (TRT, CHEMIN_MEDIA, (2, 60))]
        self.operations = {
            CHEMIN_APPAREIL: {
                "GetSystemDateAndTime": self.lire_horloge,
                "SetSystemDateAndTime": self.regler_horloge,
                "GetNTP": self.lire_ntp,
                "GetCapabilities": self.lire_capacites,
                "GetServices": self.lire_services,
            },
            CHEMIN_MEDIA: {
                "GetProfiles": self.lire_profils,
                "GetOSDs": self.lire_incrustations,
                "GetOSDOptions": self.lire_options_incrustations,
                "SetOSD": self.modifier_incrustation,
                "CreateOSD": self.creer_incrustation,
                "DeleteOSD": self.supprimer_incrustation,
                "GetStreamUri": self.lire_uri_flux,
                "GetVideoEncoderConfigurations": self.lire_encodeurs,
                "GetVideoEncoderConfigurationOptions": self.lire_options_encodeur,
                "SetVideoEncoderConfiguration": self.modifier_encodeur,
            },
        }
        if "image" in services:
            self.services.append((TIMG, CHEMIN_IMAGE, (2, 60)))
            self.operations[CHEMIN_IMAGE] = {
                "GetImagingSettings": self.lire_image,
                "GetOptions": self.lire_options_image,
                "SetImagingSettings": self.modifier_image,
            }
        if "media2" in services:
            self.services.append((TR2, CHEMIN_MEDIA_2, (2, 60)))
            self.operations[CHEMIN_MEDIA_2] = {
                "GetProfiles": self.lire_profils_2,
                "GetStreamUri": self.lire_uri_flux_2,
                "GetVideoEncoderConfigurations": self.lire_encodeurs_2,
                "GetVideoEncoderConfigurationOptions": self.lire_options_encodeur_2,
                "SetVideoEncoderConfiguration": self.modifier_encodeur_2,
            }

    def muette(self) -> bool:
        """Encodeur en cours de relance : aucune requête ne reçoit de réponse."""
        return time.monotonic() < self.muette_jusqu_a

    def _relancer_l_encodeur(self) -> None:
        if self.silence_apres_encodage_s:
            self.muette_jusqu_a = time.monotonic() + self.silence_apres_encodage_s

    def traiter(self, chemin: str, corps: bytes, hote: str) -> tuple[int, str]:
        """Requête SOAP reçue sur `chemin` → (statut HTTP, réponse SOAP). `hote` : adresse sous laquelle on nous joint."""
        try:
            try:
                enveloppe = ET.fromstring(corps)
            except ET.ParseError:
                raise Faute("ter:WellFormed", "Requête SOAP illisible") from None
            requete = enveloppe.find("env:Body/*", NS)
            if requete is None:
                raise Faute("ter:WellFormed", "Corps SOAP vide")
            nom = requete.tag.rpartition("}")[2]
            operation = self.operations[chemin].get(nom)
            if operation is None:
                raise Faute("ter:ActionNotSupported", f"Opération non prise en charge : {nom}", code="env:Receiver")
            if self.identifiants and nom not in SANS_IDENTIFIANTS:
                _verifier_identifiants(enveloppe.find("env:Header", NS), self.identifiants)
            with self.etat.verrou:
                return 200, _enveloppe(operation(requete, hote))
        except Faute as faute:
            return 400, _faute_xml(faute)

    def lire_horloge(self, _requete: ET.Element, _hote: str) -> str:
        etat = self.etat
        return (
            "<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime>"
            f"<tt:DateTimeType>{etat.mode}</tt:DateTimeType>"
            f"<tt:DaylightSavings>{str(etat.heure_ete).lower()}</tt:DaylightSavings>"
            f"<tt:TimeZone><tt:TZ>{escape(etat.fuseau)}</tt:TZ></tt:TimeZone>"
            f"<tt:UTCDateTime>{_date_heure(etat.heure())}</tt:UTCDateTime>"
            "</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>"
        )

    def regler_horloge(self, requete: ET.Element, _hote: str) -> str:
        mode = _exiger(requete, "tds:DateTimeType")
        if mode not in ("Manual", "NTP"):
            raise Faute("ter:InvalidArgVal", f"DateTimeType inconnu : {mode}")
        nouvelle_heure = None
        if mode == "Manual":
            utc = requete.find("tds:UTCDateTime", NS)
            if utc is None:
                raise Faute("ter:InvalidArgVal", "UTCDateTime exigé en mode manuel")
            try:
                nouvelle_heure = datetime(
                    *(int(_exiger(utc, f"tt:Date/tt:{c}")) for c in ("Year", "Month", "Day")),
                    *(int(_exiger(utc, f"tt:Time/tt:{c}")) for c in ("Hour", "Minute", "Second")),
                    tzinfo=UTC,
                )
            except ValueError:
                raise Faute("ter:InvalidDateTime", "Date ou heure invalide") from None
        etat = self.etat
        etat.mode = mode
        etat.heure_ete = _texte(requete, "tds:DaylightSavings") == "true"
        etat.fuseau = _texte(requete, "tds:TimeZone/tt:TZ") or etat.fuseau
        if nouvelle_heure is not None:
            etat.decalage = nouvelle_heure - datetime.now(UTC)
        return "<tds:SetSystemDateAndTimeResponse/>"

    def lire_ntp(self, _requete: ET.Element, _hote: str) -> str:
        return (
            "<tds:GetNTPResponse><tds:NTPInformation><tt:FromDHCP>false</tt:FromDHCP>"
            f"<tt:NTPManual><tt:Type>DNS</tt:Type><tt:DNSname>{escape(self.etat.serveur_ntp)}</tt:DNSname></tt:NTPManual>"
            "</tds:NTPInformation></tds:GetNTPResponse>"
        )

    def lire_capacites(self, _requete: ET.Element, hote: str) -> str:
        """Annonce les services : c'est ici que le client apprend l'adresse du service média."""
        image = (
            f"<tt:Imaging><tt:XAddr>http://{escape(hote)}{CHEMIN_IMAGE}</tt:XAddr></tt:Imaging>"
            if CHEMIN_IMAGE in self.operations
            else ""
        )
        return (
            "<tds:GetCapabilitiesResponse><tds:Capabilities>"
            f"<tt:Device><tt:XAddr>http://{escape(hote)}{CHEMIN_APPAREIL}</tt:XAddr></tt:Device>{image}"
            f"<tt:Media><tt:XAddr>http://{escape(hote)}{CHEMIN_MEDIA}</tt:XAddr>"
            "<tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP>"
            "<tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities></tt:Media>"
            "</tds:Capabilities></tds:GetCapabilitiesResponse>"
        )

    def lire_services(self, _requete: ET.Element, hote: str) -> str:
        """Annonce chaque service, comme GetCapabilities en `http://` à l'hôte joint : le média 2 n'est annoncé qu'ici."""
        services = "".join(
            f"<tds:Service><tds:Namespace>{espace}</tds:Namespace><tds:XAddr>http://{escape(hote)}{chemin}</tds:XAddr>"
            f"<tds:Version><tt:Major>{majeure}</tt:Major><tt:Minor>{mineure}</tt:Minor></tds:Version></tds:Service>"
            for espace, chemin, (majeure, mineure) in self.services
        )
        return f"<tds:GetServicesResponse>{services}</tds:GetServicesResponse>"

    def lire_profils(self, _requete: ET.Element, _hote: str) -> str:
        profils = "".join(
            f'<trt:Profiles token="{profil.token}" fixed="true"><tt:Name>{profil.nom}</tt:Name>'
            f"{_source_video_xml('tt:VideoSourceConfiguration')}"
            f"{_encodeur_xml(profil.encodeur, 'tt:VideoEncoderConfiguration')}</trt:Profiles>"
            for profil in self.profils
        )
        return f"<trt:GetProfilesResponse>{profils}</trt:GetProfilesResponse>"

    # --- Profils et encodeurs, médias 1 et 2 ---

    def _profil(self, token: str) -> Profil:
        for profil in self.profils:
            if profil.token == token:
                return profil
        raise Faute("ter:NoProfile", f"Profil inconnu : {token}")

    def _encodeur(self, token: str) -> Encodeur:
        for profil in self.profils:
            if profil.encodeur.token == token:
                return profil.encodeur
        raise Faute("ter:NoConfig", f"Configuration d'encodeur inconnue : {token}")

    def _encodeurs_demandes(self, requete: ET.Element, espace: str) -> list[Encodeur]:
        """Encodeurs choisis par `ConfigurationToken` ou `ProfileToken` ; tous sans l'un ni l'autre."""
        if configuration := _texte(requete, f"{espace}:ConfigurationToken"):
            return [self._encodeur(configuration)]
        if profil := _texte(requete, f"{espace}:ProfileToken"):
            return [self._profil(profil).encodeur]
        return [profil.encodeur for profil in self.profils]

    def _uri(self, requete: ET.Element, espace: str, hote: str) -> str:
        """URL RTSP du profil demandé, à l'hôte joint (sans son port : RTSP sur 554)."""
        profil = self._profil(_exiger(requete, f"{espace}:ProfileToken"))
        return f"rtsp://{escape(urllib.parse.urlsplit('//' + hote).hostname or hote)}{escape(profil.chemin_rtsp)}"

    @staticmethod
    def _modifier(encodeur: Encodeur, configuration: ET.Element, codec: str, gop: str) -> None:
        """Valide puis applique résolution, images par seconde, débit, qualité et GOP ; le codec ne change pas."""
        if codec != encodeur.codec:
            raise Faute("ter:ConfigModify", f"Codec non modifiable : {codec}")
        try:
            resolution = (
                int(_exiger(configuration, "tt:Resolution/tt:Width")),
                int(_exiger(configuration, "tt:Resolution/tt:Height")),
            )
        except ValueError:
            raise Faute("ter:ConfigModify", "Résolution illisible") from None
        if resolution not in encodeur.resolutions:
            raise Faute("ter:ConfigModify", f"Résolution non proposée : {resolution[0]}x{resolution[1]}")
        images = _nombre(configuration, "tt:RateControl/tt:FrameRateLimit", IMAGES_PAR_SECONDE, "ter:ConfigModify")
        debit = _nombre(configuration, "tt:RateControl/tt:BitrateLimit", encodeur.debits, "ter:ConfigModify")
        qualite = _nombre(configuration, "tt:Quality", QUALITE, "ter:ConfigModify")
        if gop and not (gop.isdigit() and GOP[0] <= int(gop) <= GOP[1]):
            raise Faute("ter:ConfigModify", f"GOP hors des bornes : {gop}")
        encodeur.resolution = resolution
        encodeur.images_par_seconde = encodeur.images_par_seconde if images is None else images
        encodeur.debit = encodeur.debit if debit is None else int(debit)
        encodeur.qualite = encodeur.qualite if qualite is None else qualite
        encodeur.gop = int(gop) if gop else encodeur.gop

    # --- Média 1 : URL de flux et encodeur (le repli d'une caméra sans média 2) ---

    def lire_uri_flux(self, requete: ET.Element, hote: str) -> str:
        return (
            f"<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>{self._uri(requete, 'trt', hote)}</tt:Uri>"
            "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>"
            "<tt:Timeout>PT0S</tt:Timeout></trt:MediaUri></trt:GetStreamUriResponse>"
        )

    def lire_encodeurs(self, _requete: ET.Element, _hote: str) -> str:
        configurations = "".join(_encodeur_xml(p.encodeur, "trt:Configurations") for p in self.profils)
        return f"<trt:GetVideoEncoderConfigurationsResponse>{configurations}</trt:GetVideoEncoderConfigurationsResponse>"

    def lire_options_encodeur(self, requete: ET.Element, _hote: str) -> str:
        """Une seule réponse au média 1 : les options du premier encodeur demandé."""
        encodeur = self._encodeurs_demandes(requete, "trt")[0]
        h264 = (
            "".join(_resolution(r, "tt:ResolutionsAvailable") for r in encodeur.resolutions)
            + _bornes("tt:GovLengthRange", GOP)
            + _bornes("tt:FrameRateRange", IMAGES_PAR_SECONDE)
            + _bornes("tt:EncodingIntervalRange", (1, 1))
            + "<tt:H264ProfilesSupported>Main</tt:H264ProfilesSupported>"
        )
        return (
            f"<trt:GetVideoEncoderConfigurationOptionsResponse><trt:Options>{_bornes('tt:QualityRange', QUALITE)}"
            f"<tt:H264>{h264}</tt:H264><tt:Extension><tt:H264>{h264}{_bornes('tt:BitrateRange', encodeur.debits)}"
            "</tt:H264></tt:Extension></trt:Options></trt:GetVideoEncoderConfigurationOptionsResponse>"
        )

    def modifier_encodeur(self, requete: ET.Element, _hote: str) -> str:
        configuration = requete.find("trt:Configuration", NS)
        if configuration is None:
            raise Faute("ter:InvalidArgVal", "Configuration manquante")
        encodeur = self._encodeur(configuration.get("token", ""))
        # Le média 1 décrit le codec en H.264 : seul ce « H.264 » renvoyé tel quel laisse le codec inchangé.
        codec = _texte(configuration, "tt:Encoding")
        if codec != "H264":
            raise Faute("ter:ConfigModify", f"Codec non modifiable : {codec}")
        self._modifier(encodeur, configuration, encodeur.codec, _texte(configuration, "tt:H264/tt:GovLength"))
        self._relancer_l_encodeur()
        return "<trt:SetVideoEncoderConfigurationResponse/>"

    # --- Média 2 ---

    def lire_profils_2(self, requete: ET.Element, _hote: str) -> str:
        """Configurations des profils seulement pour les `Type` demandés (`All`, `VideoSource`, `VideoEncoder`)."""
        types = {t.text for t in requete.findall("tr2:Type", NS)}
        token = _texte(requete, "tr2:Token")
        profils = [self._profil(token)] if token else self.profils
        reponse = ""
        for profil in profils:
            configurations = ""
            if types & {"All", "VideoSource"}:
                configurations += _source_video_xml("tr2:VideoSource")
            if types & {"All", "VideoEncoder"}:
                configurations += _encodeur_2_xml(profil.encodeur, "tr2:VideoEncoder")
            reponse += (
                f'<tr2:Profiles token="{profil.token}" fixed="true"><tr2:Name>{profil.nom}</tr2:Name>'
                f"<tr2:Configurations>{configurations}</tr2:Configurations></tr2:Profiles>"
            )
        return f"<tr2:GetProfilesResponse>{reponse}</tr2:GetProfilesResponse>"

    def lire_uri_flux_2(self, requete: ET.Element, hote: str) -> str:
        return f"<tr2:GetStreamUriResponse><tr2:Uri>{self._uri(requete, 'tr2', hote)}</tr2:Uri></tr2:GetStreamUriResponse>"

    def lire_encodeurs_2(self, requete: ET.Element, _hote: str) -> str:
        configurations = "".join(
            _encodeur_2_xml(e, "tr2:Configurations") for e in self._encodeurs_demandes(requete, "tr2")
        )
        return f"<tr2:GetVideoEncoderConfigurationsResponse>{configurations}</tr2:GetVideoEncoderConfigurationsResponse>"

    def lire_options_encodeur_2(self, requete: ET.Element, _hote: str) -> str:
        images = " ".join(str(i) for i in range(IMAGES_PAR_SECONDE[1], IMAGES_PAR_SECONDE[0] - 1, -1))
        options = "".join(
            f'<tr2:Options GovLengthRange="{GOP[0]} {GOP[1]}" FrameRatesSupported="{images}" ProfilesSupported="Main"'
            f' ConstantBitRateSupported="true"><tt:Encoding>{e.codec}</tt:Encoding>{_bornes("tt:QualityRange", QUALITE)}'
            + "".join(_resolution(r, "tt:ResolutionsAvailable") for r in e.resolutions)
            + f"{_bornes('tt:BitrateRange', e.debits)}</tr2:Options>"
            for e in self._encodeurs_demandes(requete, "tr2")
        )
        return f"<tr2:GetVideoEncoderConfigurationOptionsResponse>{options}</tr2:GetVideoEncoderConfigurationOptionsResponse>"

    def modifier_encodeur_2(self, requete: ET.Element, _hote: str) -> str:
        configuration = requete.find("tr2:Configuration", NS)
        if configuration is None:
            raise Faute("ter:InvalidArgVal", "Configuration manquante")
        encodeur = self._encodeur(configuration.get("token", ""))
        self._modifier(encodeur, configuration, _texte(configuration, "tt:Encoding"), configuration.get("GovLength", ""))
        self._relancer_l_encodeur()
        return "<tr2:SetVideoEncoderConfigurationResponse/>"

    # --- Image ---

    def _verifier_source_video(self, requete: ET.Element) -> None:
        source = _texte(requete, "timg:VideoSourceToken")
        if source != SOURCE_VIDEO:
            raise Faute("ter:NoSource", f"Source vidéo inconnue : {source}")

    def lire_image(self, requete: ET.Element, _hote: str) -> str:
        self._verifier_source_video(requete)
        image = self.etat.image
        parametres = {
            "Brightness": image.luminosite,
            "ColorSaturation": image.saturation,
            "Contrast": image.contraste,
        }
        return (
            "<timg:GetImagingSettingsResponse><timg:ImagingSettings>"
            f"<tt:BacklightCompensation><tt:Mode>{image.contre_jour}</tt:Mode></tt:BacklightCompensation>"
            + "".join(f"<tt:{nom}>{valeur:g}</tt:{nom}>" for nom, valeur in parametres.items())
            + f"<tt:IrCutFilter>{image.infrarouge}</tt:IrCutFilter><tt:Sharpness>{image.nettete:g}</tt:Sharpness>"
            f"<tt:WideDynamicRange><tt:Mode>{image.wdr}</tt:Mode><tt:Level>{image.wdr_niveau:g}</tt:Level>"
            "</tt:WideDynamicRange></timg:ImagingSettings></timg:GetImagingSettingsResponse>"
        )

    def lire_options_image(self, requete: ET.Element, _hote: str) -> str:
        self._verifier_source_video(requete)

        def modes(balise: str, valeurs: tuple[str, ...]) -> str:
            return "".join(f"<{balise}>{m}</{balise}>" for m in valeurs)

        return (
            "<timg:GetOptionsResponse><timg:ImagingOptions>"
            f"<tt:BacklightCompensation>{modes('tt:Mode', MODES_CONTRE_JOUR)}</tt:BacklightCompensation>"
            + "".join(_bornes(f"tt:{nom}", BORNES_IMAGE) for nom in ("Brightness", "ColorSaturation", "Contrast"))
            + modes("tt:IrCutFilterModes", MODES_INFRAROUGE)
            + _bornes("tt:Sharpness", BORNES_IMAGE)
            + f"<tt:WideDynamicRange>{modes('tt:Mode', MODES_WDR)}{_bornes('tt:Level', BORNES_IMAGE)}</tt:WideDynamicRange>"
            "</timg:ImagingOptions></timg:GetOptionsResponse>"
        )

    def modifier_image(self, requete: ET.Element, _hote: str) -> str:
        """Valide tout, puis applique ce qui est envoyé ; le WDR est validé mais pas appliqué (le cas « pas pris »)."""
        self._verifier_source_video(requete)
        reglages = requete.find("timg:ImagingSettings", NS)
        if reglages is None:
            raise Faute("ter:InvalidArgVal", "ImagingSettings manquant")
        changements: dict[str, float | str | None] = {
            attribut: _nombre(reglages, f"tt:{nom}", BORNES_IMAGE, "ter:InvalidArgVal")
            for nom, attribut in PARAMETRES_IMAGE.items()
        }
        changements["infrarouge"] = _mode(reglages, "tt:IrCutFilter", MODES_INFRAROUGE)
        changements["contre_jour"] = _mode(reglages, "tt:BacklightCompensation/tt:Mode", MODES_CONTRE_JOUR)
        _mode(reglages, "tt:WideDynamicRange/tt:Mode", MODES_WDR)
        _nombre(reglages, "tt:WideDynamicRange/tt:Level", BORNES_IMAGE, "ter:InvalidArgVal")
        for attribut, valeur in changements.items():
            if valeur is not None:
                setattr(self.etat.image, attribut, valeur)
        return "<timg:SetImagingSettingsResponse/>"

    def _verifier_source(self, requete: ET.Element) -> None:
        source = _texte(requete, "trt:ConfigurationToken")
        if source and source != CONFIGURATION_SOURCE:
            raise Faute("ter:InvalidArgVal", f"Configuration de source inconnue : {source}")

    def lire_incrustations(self, requete: ET.Element, _hote: str) -> str:
        self._verifier_source(requete)
        osds = "".join(_incrustation_xml(osd, "trt:OSDs") for osd in self.etat.incrustations)
        return f"<trt:GetOSDsResponse>{osds}</trt:GetOSDsResponse>"

    def lire_options_incrustations(self, requete: ET.Element, _hote: str) -> str:
        """Annonce la création des types créables (un de chaque au plus) : une Incrustation cachée peut revenir."""
        self._verifier_source(requete)
        positions = "".join(f"<tt:PositionOption>{p}</tt:PositionOption>" for p in POSITIONS)
        types = "".join(f"<tt:Type>{t}</tt:Type>" for t in self.types_creables)
        dates = "".join(f"<tt:DateFormat>{f}</tt:DateFormat>" for f in FORMATS_DATE)
        heures = "".join(f"<tt:TimeFormat>{f}</tt:TimeFormat>" for f in FORMATS_HEURE)
        return (
            "<trt:GetOSDOptionsResponse><trt:OSDOptions>"
            '<tt:MaximumNumberOfOSDs Total="2" PlainText="1" DateAndTime="1"/>'
            f"<tt:Type>Text</tt:Type>{positions}<tt:TextOption>{types}{dates}{heures}</tt:TextOption>"
            "</trt:OSDOptions></trt:GetOSDOptionsResponse>"
        )

    def _osd_demandee(self, requete: ET.Element) -> ET.Element:
        osd = requete.find("trt:OSD", NS)
        if osd is None:
            raise Faute("ter:InvalidArgVal", "OSD manquant")
        if _texte(osd, "tt:VideoSourceConfigurationToken") != CONFIGURATION_SOURCE:
            raise Faute("ter:InvalidArgVal", "Configuration de source inconnue")
        return osd

    def _index(self, token: str) -> int:
        for index, osd in enumerate(self.etat.incrustations):
            if osd.token == token:
                return index
        raise Faute("ter:InvalidArgVal", f"Incrustation inconnue : {token}")

    def modifier_incrustation(self, requete: ET.Element, _hote: str) -> str:
        osd = self._osd_demandee(requete)
        token = osd.get("token", "")
        index = self._index(token)
        nouvelle = _lire_incrustation(osd, token)
        if nouvelle.type_texte != self.etat.incrustations[index].type_texte:
            raise Faute("ter:InvalidArgVal", "Le type de texte d'une Incrustation ne change pas")
        self.etat.incrustations[index] = nouvelle
        return "<trt:SetOSDResponse/>"

    def creer_incrustation(self, requete: ET.Element, _hote: str) -> str:
        etat = self.etat
        nouvelle = _lire_incrustation(self._osd_demandee(requete), f"OSD_{etat.prochain_token}")
        if nouvelle.type_texte not in self.types_creables:
            raise Faute("ter:InvalidArgVal", f"Création d'une Incrustation {nouvelle.type_texte} non prise en charge")
        if any(osd.type_texte == nouvelle.type_texte for osd in etat.incrustations):
            raise Faute("ter:MaxOSDs", f"Déjà une Incrustation {nouvelle.type_texte}", code="env:Receiver")
        etat.prochain_token += 1
        etat.incrustations.append(nouvelle)
        return f"<trt:CreateOSDResponse><trt:OSDToken>{nouvelle.token}</trt:OSDToken></trt:CreateOSDResponse>"

    def supprimer_incrustation(self, requete: ET.Element, _hote: str) -> str:
        del self.etat.incrustations[self._index(_exiger(requete, "trt:OSDToken"))]
        return "<trt:DeleteOSDResponse/>"


# --- Serveur HTTP -----------------------------------------------------------------------------------------------


def assurer_certificat(certificat: str, cle: str) -> None:
    """Crée un certificat auto-signé et sa clé s'ils n'existent pas ; sinon les garde, pour une clé stable."""
    if os.path.exists(certificat) and os.path.exists(cle):
        return
    subprocess.run(
        [
            OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
            "-subj", "/CN=camera-simulee-onvif", "-keyout", cle, "-out", certificat,
        ],
        check=True,
        capture_output=True,
    )


# Versions de `ONVIF_TLS_MAX`.
VERSIONS_TLS = {
    "1.0": ssl.TLSVersion.TLSv1,
    "1.1": ssl.TLSVersion.TLSv1_1,
    "1.2": ssl.TLSVersion.TLSv1_2,
    "1.3": ssl.TLSVersion.TLSv1_3,
}


def _nom_operation(corps: bytes) -> str:
    """Nom de l'opération SOAP d'une requête (`SetImagingSettings`…), vide si illisible."""
    try:
        requete = ET.fromstring(corps).find("env:Body/*", NS)
    except ET.ParseError:
        return ""
    return "" if requete is None else requete.tag.rpartition("}")[2]


def creer_serveur(
    adresse: str,
    port: int,
    camera: Camera,
    certificat: tuple[str, str] | None = None,
    tls_max: ssl.TLSVersion | None = None,
) -> ThreadingHTTPServer:
    """Serveur de `camera` en HTTP, ou en HTTPS avec `certificat` (chemins du certificat et de sa clé).

    `tls_max` : version TLS la plus haute servie ; sous TLS 1.2, celle d'une caméra ancienne.
    """
    schema = "https" if certificat else "http"

    class Requetes(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.operation_soap = ""
            if self.path not in camera.operations:
                self.send_error(404)
                return
            corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if camera.muette():
                # Connexion fermée sans réponse, comme une caméra qui relance son encodeur.
                self.close_connection = True
                return
            hote = self.headers.get("Host") or f"{self.server.server_address[0]}:{self.server.server_address[1]}"
            statut, reponse = camera.traiter(self.path, corps, hote)
            self.operation_soap = _nom_operation(corps)
            donnees = reponse.encode()
            self.send_response(statut)
            self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, format: str, *args) -> None:
            # Nom de l'opération SOAP en fin de ligne : les tests y lisent ce qui a été envoyé (ou pas).
            operation = getattr(self, "operation_soap", "")  # absent : requête rejetée avant do_POST
            sys.stderr.write(
                f"{self.address_string()} {schema}:{self.server.server_address[1]} {format % args} {operation}".rstrip()
                + "\n"
            )

    serveur = ThreadingHTTPServer((adresse, port), Requetes)
    if certificat:
        contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexte.minimum_version = ssl.TLSVersion.TLSv1_2
        if tls_max is not None:
            if tls_max < ssl.TLSVersion.TLSv1_2:
                # Caméra ancienne simulée : OpenSSL 3 n'accepte TLS 1.0 et 1.1 qu'au niveau de sécurité 0.
                contexte.minimum_version = tls_max  # NOSONAR : simulation d'une caméra ancienne, jamais en prod
                contexte.set_ciphers("DEFAULT:@SECLEVEL=0")  # NOSONAR : simulation d'une caméra ancienne
            contexte.maximum_version = tls_max
        contexte.load_cert_chain(*certificat)
        # Poignée de main dans le fil de chaque requête, pas dans celui qui accepte les connexions.
        serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True, do_handshake_on_connect=False)
    return serveur


def sonder(port: int, https: bool) -> None:
    """Healthcheck : le service local répond à GetSystemDateAndTime."""
    contexte = None
    if https:
        # Sonde locale du certificat auto-signé de la simulation : rien à vérifier.
        contexte = ssl.create_default_context()  # NOSONAR : sonde locale d'un certificat auto-signé de dev
        contexte.check_hostname = False  # NOSONAR : sonde locale d'un certificat auto-signé de dev
        contexte.verify_mode = ssl.CERT_NONE  # NOSONAR : sonde locale d'un certificat auto-signé de dev
        # Toute version servie, `ONVIF_TLS_MAX` compris : OpenSSL 3 n'accepte TLS 1.0 et 1.1 qu'au niveau 0.
        contexte.minimum_version = ssl.TLSVersion.TLSv1  # NOSONAR : sonde locale d'une caméra ancienne simulée
        contexte.set_ciphers("DEFAULT:@SECLEVEL=0")  # NOSONAR : sonde locale d'une caméra ancienne simulée
    requete = urllib.request.Request(
        f"{'https' if https else 'http'}://127.0.0.1:{port}{CHEMIN_APPAREIL}",
        data=_enveloppe("<tds:GetSystemDateAndTime/>").encode(),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
    )
    with urllib.request.urlopen(requete, timeout=3, context=contexte) as reponse:
        if b"GetSystemDateAndTimeResponse" not in reponse.read():
            raise SystemExit(1)


def _ports() -> dict[bool, int]:
    """Ports servis, par `https` : ceux qui sont renseignés, ou HTTP sur 80 si aucun."""
    ports = {
        https: int(valeur)
        for https, valeur in ((False, os.environ.get("ONVIF_PORT")), (True, os.environ.get("ONVIF_PORT_HTTPS")))
        if valeur
    }
    return ports or {False: 80}


def _liste(variable: str) -> tuple[str, ...]:
    """Valeurs d'une variable d'environnement séparées par des virgules ; vide si elle ne l'est pas."""
    return tuple(v.strip() for v in os.environ.get(variable, "").split(",") if v.strip())


def main() -> None:
    ports = _ports()
    if sys.argv[1:] == ["sonde"]:
        for https, port in ports.items():
            sonder(port, https)
        return
    certificat = None
    if True in ports:
        certificat = (os.environ.get("ONVIF_CERTIFICAT", ""), os.environ.get("ONVIF_CLE", ""))
        if not all(certificat):
            raise SystemExit("HTTPS : ONVIF_CERTIFICAT et ONVIF_CLE exigés")
        assurer_certificat(*certificat)
    identifiant, mot_de_passe = os.environ.get("ONVIF_IDENTIFIANT", ""), os.environ.get("ONVIF_MOT_DE_PASSE", "")
    identifiants = (identifiant, mot_de_passe) if identifiant and mot_de_passe else None
    types = _liste("ONVIF_TYPES_CREABLES") or TYPES_TEXTE
    services = frozenset(_liste("ONVIF_SERVICES"))
    if inconnus := services - set(SERVICES):
        raise SystemExit(f"ONVIF_SERVICES : services inconnus {', '.join(sorted(inconnus))}")
    camera = Camera(
        identifiants,
        types,
        services,
        _liste("ONVIF_CHEMINS_RTSP") or CHEMINS_RTSP,
        float(os.environ.get("ONVIF_SILENCE_APRES_ENCODAGE_S") or 0),
    )
    tls_max = VERSIONS_TLS[os.environ["ONVIF_TLS_MAX"]] if os.environ.get("ONVIF_TLS_MAX") else None
    fils = []
    for https, port in ports.items():
        serveur = creer_serveur("0.0.0.0", port, camera, certificat if https else None, tls_max)
        fils.append(threading.Thread(target=serveur.serve_forever))
        print(
            f"Caméra simulée ONVIF en {'HTTPS' if https else 'HTTP'} sur le port {port}, "
            f"{'avec' if identifiants else 'sans'} identifiants, services {', '.join(sorted(services)) or 'de base'}",
            flush=True,
        )
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()


if __name__ == "__main__":
    main()
