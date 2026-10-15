"""Caméra simulée ONVIF : service SOAP 1.2 en bibliothèque standard, état en mémoire, « sortie d'usine » au démarrage.

Seulement les opérations dont ArgOS se sert pour les Réglages de la Caméra (README.md). Lancé dans le réseau
d'une Caméra simulée (compose.simulation.yaml), il lui donne une interface ONVIF : même IP, même MAC.

Configuration par variables d'environnement : `ONVIF_PORT` (HTTP) et `ONVIF_PORT_HTTPS` (HTTPS), l'un, l'autre
ou les deux (HTTP sur 80 si aucun) ; en HTTPS, `ONVIF_CERTIFICAT` et `ONVIF_CLE` (chemins du certificat et de sa clé,
créés auto-signés s'ils n'existent pas) ; `ONVIF_IDENTIFIANT` et `ONVIF_MOT_DE_PASSE` (WS-Security exigé seulement
s'ils sont tous deux renseignés), `ONVIF_TYPES_CREABLES` (types d'Incrustation que la caméra sait recréer, séparés
par des virgules ; les deux par défaut). HTTP et HTTPS servent la même caméra (même état).
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
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape, quoteattr

CHEMIN_APPAREIL = "/onvif/device_service"
CHEMIN_MEDIA = "/onvif/media_service"
OPENSSL = "/usr/bin/openssl"

# Espaces de noms XML : des noms imposés par SOAP et ONVIF, jamais appelés (NOSONAR définitif).
ENV = "http://www.w3.org/2003/05/soap-envelope"  # NOSONAR
TDS = "http://www.onvif.org/ver10/device/wsdl"  # NOSONAR
TRT = "http://www.onvif.org/ver10/media/wsdl"  # NOSONAR
TT = "http://www.onvif.org/ver10/schema"  # NOSONAR
TER = "http://www.onvif.org/ver10/error"  # NOSONAR
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"  # NOSONAR
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"  # NOSONAR
NS = {"env": ENV, "tds": TDS, "trt": TRT, "tt": TT, "wsse": WSSE, "wsu": WSU}

# Seule opération lue sans identifiants, comme sur les vraies caméras : le client y lit l'heure de la caméra.
SANS_IDENTIFIANTS = {"GetSystemDateAndTime"}

PROFIL = "Profile_1"
SOURCE_VIDEO = "VideoSource_1"
CONFIGURATION_SOURCE = "VideoSourceConfig_1"
POSITIONS = ("UpperLeft", "UpperRight", "LowerLeft", "LowerRight", "Custom")
FORMATS_DATE = ("yyyy-MM-dd", "MM/dd/yyyy", "dd/MM/yyyy")
FORMATS_HEURE = ("HH:mm:ss", "hh:mm:ss tt")
TYPES_TEXTE = ("Plain", "DateAndTime")
# Texte incrusté le plus long accepté : au-delà, faute, comme beaucoup de caméras.
LONGUEUR_MAX_TEXTE = 32


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
        hashlib.sha1(nonce + _texte(jeton, "wsu:Created").encode() + mot_de_passe.encode()).digest()  # NOSONAR : SHA-1 imposé par WS-Security, risque traité en 0.6.3
    ).decode()
    bon_identifiant = hmac.compare_digest(_texte(jeton, "wsse:Username"), identifiant)
    bonne_empreinte = hmac.compare_digest(_texte(jeton, "wsse:Password"), attendue)
    if not (bon_identifiant and bonne_empreinte):
        raise Faute("ter:NotAuthorized", "Identifiants refusés")


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


class Camera:
    def __init__(
        self, identifiants: tuple[str, str] | None = None, types_creables: tuple[str, ...] = TYPES_TEXTE
    ) -> None:
        self.identifiants = identifiants
        self.types_creables = types_creables
        self.etat = Etat()
        self.operations = {
            CHEMIN_APPAREIL: {
                "GetSystemDateAndTime": self.lire_horloge,
                "SetSystemDateAndTime": self.regler_horloge,
                "GetNTP": self.lire_ntp,
                "GetCapabilities": self.lire_capacites,
            },
            CHEMIN_MEDIA: {
                "GetProfiles": self.lire_profils,
                "GetOSDs": self.lire_incrustations,
                "GetOSDOptions": self.lire_options_incrustations,
                "SetOSD": self.modifier_incrustation,
                "CreateOSD": self.creer_incrustation,
                "DeleteOSD": self.supprimer_incrustation,
            },
        }

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
        return (
            "<tds:GetCapabilitiesResponse><tds:Capabilities>"
            f"<tt:Device><tt:XAddr>http://{escape(hote)}{CHEMIN_APPAREIL}</tt:XAddr></tt:Device>"
            f"<tt:Media><tt:XAddr>http://{escape(hote)}{CHEMIN_MEDIA}</tt:XAddr>"
            "<tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP>"
            "<tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities></tt:Media>"
            "</tds:Capabilities></tds:GetCapabilitiesResponse>"
        )

    def lire_profils(self, _requete: ET.Element, _hote: str) -> str:
        return (
            f'<trt:GetProfilesResponse><trt:Profiles token="{PROFIL}" fixed="true"><tt:Name>mainStream</tt:Name>'
            f'<tt:VideoSourceConfiguration token="{CONFIGURATION_SOURCE}"><tt:Name>VideoSourceConfig</tt:Name>'
            f"<tt:UseCount>1</tt:UseCount><tt:SourceToken>{SOURCE_VIDEO}</tt:SourceToken>"
            '<tt:Bounds x="0" y="0" width="1280" height="720"/></tt:VideoSourceConfiguration>'
            "</trt:Profiles></trt:GetProfilesResponse>"
        )

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


def creer_serveur(
    adresse: str, port: int, camera: Camera, certificat: tuple[str, str] | None = None
) -> ThreadingHTTPServer:
    """Serveur de `camera` en HTTP, ou en HTTPS avec `certificat` (chemins du certificat et de sa clé)."""

    class Requetes(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path not in camera.operations:
                self.send_error(404)
                return
            corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            hote = self.headers.get("Host") or f"{self.server.server_address[0]}:{self.server.server_address[1]}"
            statut, reponse = camera.traiter(self.path, corps, hote)
            donnees = reponse.encode()
            self.send_response(statut)
            self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, format: str, *args) -> None:
            sys.stderr.write(f"{self.address_string()} {format % args}\n")

    serveur = ThreadingHTTPServer((adresse, port), Requetes)
    if certificat:
        contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexte.minimum_version = ssl.TLSVersion.TLSv1_2
        contexte.load_cert_chain(*certificat)
        # Poignée de main dans le fil de chaque requête, pas dans celui qui accepte les connexions.
        serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True, do_handshake_on_connect=False)
    return serveur


def sonder(port: int, https: bool) -> None:
    """Healthcheck : le service local répond à GetSystemDateAndTime."""
    contexte = None
    if https:
        # Sonde locale du certificat auto-signé de la simulation : rien à vérifier.
        contexte = ssl.create_default_context()
        contexte.check_hostname = False  # NOSONAR : sonde locale d'un certificat auto-signé de dev
        contexte.verify_mode = ssl.CERT_NONE  # NOSONAR : sonde locale d'un certificat auto-signé de dev
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
    types = tuple(t.strip() for t in (os.environ.get("ONVIF_TYPES_CREABLES") or ",".join(TYPES_TEXTE)).split(",") if t.strip())
    camera = Camera(identifiants, types)
    fils = []
    for https, port in ports.items():
        serveur = creer_serveur("0.0.0.0", port, camera, certificat if https else None)
        fils.append(threading.Thread(target=serveur.serve_forever))
        print(
            f"Caméra simulée ONVIF en {'HTTPS' if https else 'HTTP'} sur le port {port}, "
            f"{'avec' if identifiants else 'sans'} identifiants",
            flush=True,
        )
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()


if __name__ == "__main__":
    main()
