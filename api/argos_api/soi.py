"""ArgOS lui-même, jamais Candidat d'une Détection.

Deux façons de le reconnaître, sans rien savoir de la simulation :
- ses conteneurs : les adresses de `api` et celles du pont (résolues par son nom Compose) ;
- toute machine qui publie cette API (l'hôte du Site, vu par son adresse locale ou par la passerelle
  d'un réseau Docker) : elle renvoie le jeton de cette instance sur l'origine HTTPS du Site (ADR 0005), en
  présentant exactement le certificat du Site (signé par l'Autorité du Site ou fourni par l'Administrateur) :
  seule cette machine a sa clé.

Depuis la 0.6.2, l'hôte du Site ne publie plus le RTSP du pont (ADR 0006) : il ne répond plus à l'`OPTIONS`
et n'est donc plus Candidat. Ce second contrôle n'est plus qu'un garde-fou : il ne joue que si `8554` (ou
`554`) est republié sur l'hôte.
"""

import http.client
import json
import secrets
import socket
import ssl
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from ipaddress import IPv4Address
from pathlib import Path

from cryptography import x509

# Change à chaque démarrage : seule cette instance de l'API le connaît.
JETON_INSTANCE = secrets.token_hex(16)
CHEMIN_INSTANCE = "/api/instance"
# Certificat présenté par le Site, monté seul par compose.yaml (sans sa clé) ; chaîne éventuelle à la suite.
CERTIFICAT_DU_SITE = Path("/etc/argos/serveur.crt")
_FIN_PEM = "-----END CERTIFICATE-----"


def adresses_des_conteneurs(hotes: Iterable[str]) -> set[IPv4Address]:
    """Adresses IPv4 de ce conteneur et des `hotes` (noms Compose) ; un nom introuvable est ignoré."""
    adresses = set(socket.gethostbyname_ex(socket.gethostname())[2])
    for hote in hotes:
        try:
            adresses |= {info[4][0] for info in socket.getaddrinfo(hote, None, socket.AF_INET)}
        except OSError:
            continue
    return {IPv4Address(adresse) for adresse in adresses}


def publient_cette_api(ips: Iterable[IPv4Address], port_https: int, delai: float) -> set[IPv4Address]:
    """Celles des `ips` qui répondent, sur le port HTTPS du Site, le jeton de cette instance.

    Le jeton ne compte que si le certificat présenté est celui du Site ; sans lui lisible, aucune.
    """
    ips = sorted(set(ips))
    if not ips:
        return set()
    try:
        pem = _certificat_du_site()
        # Seul certificat de confiance : celui du Site, ancre à lui seul (chaîne partielle), car api ne
        # connaît pas l'Autorité du Site et un certificat fourni par l'Administrateur n'en a pas.
        contexte = ssl.create_default_context(cadata=pem)
        contexte.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        nom = _un_nom(pem)
    except (OSError, ValueError, ssl.SSLError):
        return set()
    # L'adresse demandée (passerelle Docker, IP d'un Candidat) n'est pas forcément un des noms du
    # certificat : le nom vérifié est le sien ; le certificat présenté est en plus comparé octet pour octet.
    attendu = ssl.PEM_cert_to_DER_cert(pem)
    with ThreadPoolExecutor(len(ips)) as appels:
        reponses = list(appels.map(lambda ip: _jeton(ip, port_https, contexte, nom, attendu, delai), ips))
    return {ip for ip, jeton in zip(ips, reponses, strict=True) if jeton == JETON_INSTANCE}


def _certificat_du_site() -> str:
    """Le certificat du Site (PEM), premier de son fichier."""
    pem = CERTIFICAT_DU_SITE.read_text()
    return pem[: pem.index(_FIN_PEM) + len(_FIN_PEM)].strip() + "\n"


def _un_nom(pem: str) -> str:
    """Premier nom (DNS ou IP) du certificat du Site."""
    try:
        noms = x509.load_pem_x509_certificate(pem.encode()).extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as absente:
        raise ValueError("certificat du Site sans nom") from absente
    for nom in noms.get_values_for_type(x509.DNSName) + noms.get_values_for_type(x509.IPAddress):
        return str(nom)
    raise ValueError("certificat du Site sans nom")


def _jeton(
    ip: IPv4Address, port_https: int, contexte: ssl.SSLContext, nom: str, attendu: bytes, delai: float
) -> str | None:
    connexion = http.client.HTTPConnection(str(ip), port_https, timeout=delai)
    try:
        with socket.create_connection((str(ip), port_https), timeout=delai) as brut:
            connexion.sock = contexte.wrap_socket(brut, server_hostname=nom)
        if connexion.sock.getpeercert(binary_form=True) != attendu:
            return None
        connexion.request("GET", CHEMIN_INSTANCE, headers={"Host": nom})
        return json.load(connexion.getresponse()).get("instance")
    except (OSError, ValueError, AttributeError):
        return None
    finally:
        connexion.close()
