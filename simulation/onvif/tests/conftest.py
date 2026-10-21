"""Fixtures : une Caméra simulée ONVIF lancée dans le processus des tests, interrogée en SOAP par HTTP ou HTTPS.

`camera` répond sans identifiants (comme la Caméra simulée 4) ; `camera_protegee` exige ceux de la
Caméra simulée 2 ; `camera_complete` est la Caméra simulée 2 (identifiants, service image, média 2, deux profils
aux chemins Dahua) et `camera_sans_media_2` la même sans média 2 ; `camera_sans_recreation_de_la_date` ne sait
recréer que le nom ; `camera_https_et_http` est une seule caméra avec identifiants, service image et média 2, jointe
en HTTPS et en HTTP (comme la Caméra simulée 2), certificat créé dans un dossier temporaire ; `serveur_ntp` est un
petit serveur NTP de test, que `camera_et_serveur_ntp` joint à la place du port 123, comme
`camera_paresseuse_et_serveur_ntp`, une caméra « NTP paresseux » qui dérive vite.
Chaque test part d'une caméra neuve, « sortie d'usine ».
"""

import base64
import contextlib
import hashlib
import os
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from xml.sax.saxutils import escape

import pytest

import camera_onvif
from camera_onvif import assurer_certificat, creer_serveur

IDENTIFIANTS = ("admin", "argos-simulee")
CHEMIN_APPAREIL = "/onvif/device_service"

NS = {
    "env": "http://www.w3.org/2003/05/soap-envelope",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
    "ter": "http://www.onvif.org/ver10/error",
    "timg": "http://www.onvif.org/ver20/imaging/wsdl",
    "tr2": "http://www.onvif.org/ver20/media/wsdl",
}
NS_IMAGE = NS["timg"]
NS_MEDIA_2 = NS["tr2"]
CHEMINS_RTSP_2 = ("/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor?channel=1&subtype=1")


@dataclass
class Reponse:
    statut: int
    xml: ET.Element

    def trouver(self, chemin: str) -> ET.Element:
        element = self.xml.find(chemin, NS)
        assert element is not None, f"{chemin} absent de {ET.tostring(self.xml, encoding='unicode')}"
        return element

    def texte(self, chemin: str) -> str:
        return self.trouver(chemin).text or ""

    @property
    def faute(self) -> str | None:
        """Sous-code de la faute SOAP (ex. `ter:NotAuthorized`), ou None si la réponse n'en est pas une."""
        sous_codes = self.xml.findall(".//env:Fault/env:Code/env:Subcode/env:Value", NS)
        if self.xml.find(".//env:Fault", NS) is None:
            return None
        return sous_codes[-1].text if sous_codes else ""


def entete_securite(identifiant: str, mot_de_passe: str) -> str:
    """WS-Security UsernameToken, mot de passe en empreinte : Base64(SHA1(nonce + created + mot de passe))."""
    nonce = os.urandom(16)
    cree = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    empreinte = base64.b64encode(hashlib.sha1(nonce + cree.encode() + mot_de_passe.encode()).digest()).decode()
    return (
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
        ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{escape(identifiant)}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0'
        f'#PasswordDigest">{empreinte}</wsse:Password>'
        '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0'
        f'#Base64Binary">{base64.b64encode(nonce).decode()}</wsse:Nonce>'
        f"<wsu:Created>{cree}</wsu:Created>"
        "</wsse:UsernameToken></wsse:Security>"
    )


def contexte_sans_verification() -> ssl.SSLContext:
    """Client TLS qui accepte le certificat auto-signé de la simulation : il est comparé à part, quand il compte."""
    contexte = ssl.create_default_context()
    contexte.check_hostname = False
    contexte.verify_mode = ssl.CERT_NONE
    return contexte


def certificat_presente(adresse: tuple[str, int]) -> bytes:
    """Certificat (DER) que présente un service HTTPS."""
    with socket.create_connection(adresse, timeout=5) as brut:
        with contexte_sans_verification().wrap_socket(brut) as tls:
            return tls.getpeercert(binary_form=True)


class Camera:
    def __init__(self, url: str, identifiants: tuple[str, str] | None) -> None:
        self.url = url
        self.identifiants = identifiants
        self.contexte = contexte_sans_verification() if url.startswith("https://") else None

    def appeler(self, corps: str, chemin: str = CHEMIN_APPAREIL, identifiants: tuple[str, str] | None = ...) -> Reponse:
        """Envoie une opération SOAP 1.2 (`corps` : l'élément de l'opération, préfixes tds/trt/tt déclarés)."""
        identifiants = self.identifiants if identifiants is ... else identifiants
        entete = f"<env:Header>{entete_securite(*identifiants)}</env:Header>" if identifiants else ""
        enveloppe = (
            f'<env:Envelope xmlns:env="{NS["env"]}" xmlns:tds="{NS["tds"]}" xmlns:trt="{NS["trt"]}"'
            f' xmlns:tt="{NS["tt"]}" xmlns:timg="{NS["timg"]}" xmlns:tr2="{NS["tr2"]}">{entete}<env:Body>{corps}</env:Body></env:Envelope>'
        )
        requete = urllib.request.Request(
            self.url + chemin,
            data=enveloppe.encode(),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(requete, timeout=5, context=self.contexte) as reponse:
                return Reponse(reponse.status, ET.fromstring(reponse.read()))
        except urllib.error.HTTPError as erreur:
            return Reponse(erreur.code, ET.fromstring(erreur.read()))

    def adresse_media(self) -> str:
        """Adresse du service média, telle que la caméra l'annonce (GetCapabilities)."""
        return self.appeler('<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>').texte(
            ".//tt:Media/tt:XAddr"
        )

    def chemin_media(self) -> str:
        """Chemin du service média annoncé : seul le chemin sert, comme chez ArgOS (une caméra jointe en HTTPS
        annonce souvent `http://…`)."""
        return urllib.parse.urlsplit(self.adresse_media()).path

    def media(self, corps: str) -> Reponse:
        return self.appeler(corps, chemin=self.chemin_media())

    def services(self) -> dict[str, str]:
        """Adresses des services annoncés par `GetServices`, par espace de noms."""
        reponse = self.appeler("<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>")
        assert reponse.statut == 200
        return {
            service.findtext("tds:Namespace", namespaces=NS): service.findtext("tds:XAddr", namespaces=NS)
            for service in reponse.xml.findall(".//tds:Service", NS)
        }

    def _service(self, espace: str, corps: str, identifiants) -> Reponse:
        chemin = urllib.parse.urlsplit(self.services()[espace]).path
        return self.appeler(corps, chemin=chemin, identifiants=identifiants)

    def image(self, corps: str, identifiants: tuple[str, str] | None = ...) -> Reponse:
        return self._service(NS_IMAGE, corps, identifiants)

    def media_2(self, corps: str, identifiants: tuple[str, str] | None = ...) -> Reponse:
        return self._service(NS_MEDIA_2, corps, identifiants)


def _lancer(identifiants: tuple[str, str] | None, types_creables: tuple[str, ...] | None = None, **options):
    camera = camera_onvif.Camera(identifiants, *([types_creables] if types_creables else []), **options)
    with _servir(camera) as url:
        yield Camera(url, identifiants)


@contextlib.contextmanager
def _servir(camera: camera_onvif.Camera, certificat: tuple[str, str] | None = None):
    """Sert `camera` sur un port libre, en HTTPS avec `certificat` ; donne son URL de base."""
    serveur = creer_serveur("127.0.0.1", 0, camera, certificat)
    fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    fil.start()
    try:
        yield f"{'https' if certificat else 'http'}://127.0.0.1:{serveur.server_address[1]}"
    finally:
        serveur.shutdown()
        serveur.server_close()


@pytest.fixture
def camera():
    yield from _lancer(None)


@pytest.fixture
def camera_protegee():
    yield from _lancer(IDENTIFIANTS)


@pytest.fixture
def camera_sans_recreation_de_la_date():
    """Comme `camera`, mais n'annonce ni ne sait recréer l'Incrustation de la date et de l'heure."""
    yield from _lancer(None, ("Plain",))


@pytest.fixture
def camera_complete():
    """Comme la Caméra simulée 2 : identifiants, service image, média 2, deux profils aux chemins Dahua."""
    yield from _lancer(IDENTIFIANTS, services=frozenset({"image", "media2"}), chemins_rtsp=CHEMINS_RTSP_2)


@pytest.fixture
def camera_sans_media_2():
    """La Caméra simulée 2 lancée sans média 2 : le repli média 1 sur un Flux H.264."""
    yield from _lancer(IDENTIFIANTS, services=frozenset({"image"}), chemins_rtsp=CHEMINS_RTSP_2)


# Secondes entre l'époque NTP (1900) et l'époque Unix (1970).
EPOQUE_NTP = 2_208_988_800


class ServeurNtp:
    """Petit serveur NTP de test (version 4, mode serveur) sur 127.0.0.1, `avance` secondes en avance sur l'heure
    réelle ; compte les requêtes reçues."""

    def __init__(self, avance: float = 0) -> None:
        self.avance = avance
        self.requetes = 0
        self.prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.prise.bind(("127.0.0.1", 0))
        self.port = self.prise.getsockname()[1]
        threading.Thread(target=self._repondre, daemon=True).start()

    def _horodatage(self) -> bytes:
        secondes = time.time() + self.avance + EPOQUE_NTP
        return struct.pack("!II", int(secondes), int(secondes % 1 * 2**32))

    def _repondre(self) -> None:
        while True:
            try:
                requete, client = self.prise.recvfrom(512)
            except OSError:
                return
            self.requetes += 1
            reception = self._horodatage()
            # LI 0, version 4, mode 4 (serveur), strate 1 ; origine = émission du client.
            entete = bytes([0x24, 1, 6, 0xEC]) + bytes(8) + b"TEST" + reception
            self.prise.sendto(entete + requete[40:48] + reception + self._horodatage(), client)

    def fermer(self) -> None:
        self.prise.close()


@pytest.fixture
def serveur_ntp():
    serveur = ServeurNtp()
    yield serveur
    serveur.fermer()


@pytest.fixture
def camera_et_serveur_ntp(serveur_ntp):
    """Caméra sans identifiants qui joint ses serveurs NTP sur le port du `serveur_ntp` de test (pas 123)."""
    camera = camera_onvif.Camera(port_ntp=serveur_ntp.port)
    with _servir(camera) as url:
        yield Camera(url, None), camera, serveur_ntp


# Dérive de la caméra « NTP paresseux » de test, accélérée : 2 s par seconde.
DERIVE_PARESSEUSE_S_PAR_H = 7200


@pytest.fixture
def camera_paresseuse_et_serveur_ntp(serveur_ntp):
    """Caméra « NTP paresseux » (se cale au démarrage et sur SetNTP seulement, puis dérive de
    `DERIVE_PARESSEUSE_S_PAR_H`), qui joint le `serveur_ntp` de test."""
    camera = camera_onvif.Camera(port_ntp=serveur_ntp.port, ntp_paresseux=DERIVE_PARESSEUSE_S_PAR_H)
    with _servir(camera) as url:
        yield Camera(url, None), camera, serveur_ntp


@dataclass
class CameraHttpsEtHttp:
    https: Camera
    http: Camera
    certificat: str


@pytest.fixture
def camera_https_et_http(tmp_path):
    certificat = (str(tmp_path / "certificat.pem"), str(tmp_path / "cle.pem"))
    assurer_certificat(*certificat)
    camera = camera_onvif.Camera(IDENTIFIANTS, services=frozenset({"image", "media2"}))
    with _servir(camera, certificat) as url_https, _servir(camera) as url_http:
        yield CameraHttpsEtHttp(Camera(url_https, IDENTIFIANTS), Camera(url_http, IDENTIFIANTS), certificat[0])
