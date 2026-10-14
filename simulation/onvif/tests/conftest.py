"""Fixtures : une Caméra simulée ONVIF lancée dans le processus des tests, interrogée en SOAP par HTTP.

`camera` répond sans identifiants (comme la Caméra simulée 4) ; `camera_protegee` exige ceux de la
Caméra simulée 2 ; `camera_sans_recreation_de_la_date` ne sait recréer que le nom. Chaque test part d'une caméra neuve, « sortie d'usine ».
"""

import base64
import hashlib
import os
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from xml.sax.saxutils import escape

import pytest

from camera_onvif import creer_serveur

IDENTIFIANTS = ("admin", "argos-simulee")
CHEMIN_APPAREIL = "/onvif/device_service"

NS = {
    "env": "http://www.w3.org/2003/05/soap-envelope",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
    "ter": "http://www.onvif.org/ver10/error",
}


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


class Camera:
    def __init__(self, url: str, identifiants: tuple[str, str] | None) -> None:
        self.url = url
        self.identifiants = identifiants

    def appeler(self, corps: str, chemin: str = CHEMIN_APPAREIL, identifiants: tuple[str, str] | None = ...) -> Reponse:
        """Envoie une opération SOAP 1.2 (`corps` : l'élément de l'opération, préfixes tds/trt/tt déclarés)."""
        identifiants = self.identifiants if identifiants is ... else identifiants
        entete = f"<env:Header>{entete_securite(*identifiants)}</env:Header>" if identifiants else ""
        enveloppe = (
            f'<env:Envelope xmlns:env="{NS["env"]}" xmlns:tds="{NS["tds"]}" xmlns:trt="{NS["trt"]}"'
            f' xmlns:tt="{NS["tt"]}">{entete}<env:Body>{corps}</env:Body></env:Envelope>'
        )
        requete = urllib.request.Request(
            self.url + chemin,
            data=enveloppe.encode(),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(requete, timeout=5) as reponse:
                return Reponse(reponse.status, ET.fromstring(reponse.read()))
        except urllib.error.HTTPError as erreur:
            return Reponse(erreur.code, ET.fromstring(erreur.read()))

    def chemin_media(self) -> str:
        """Chemin du service média, tel que la caméra l'annonce (GetCapabilities)."""
        adresse = self.appeler('<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>').texte(
            ".//tt:Media/tt:XAddr"
        )
        assert adresse.startswith(self.url), adresse
        return adresse.removeprefix(self.url)

    def media(self, corps: str) -> Reponse:
        return self.appeler(corps, chemin=self.chemin_media())


def _lancer(identifiants: tuple[str, str] | None, types_creables: tuple[str, ...] | None = None):
    serveur = creer_serveur("127.0.0.1", 0, identifiants, *([types_creables] if types_creables else []))
    fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    fil.start()
    try:
        yield Camera(f"http://127.0.0.1:{serveur.server_address[1]}", identifiants)
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
