"""ArgOS lui-même, jamais Candidat d'une Détection.

Deux façons de le reconnaître, sans rien savoir de la simulation :
- ses conteneurs : les adresses de `api` et celles du pont (résolues par son nom Compose) ;
- toute machine qui publie cette API (l'hôte du Site, vu par son adresse locale ou par la passerelle
  d'un réseau Docker) : elle publie aussi le pont, et renvoie le jeton de cette instance sur l'origine
  HTTPS du Site (ADR 0005), en présentant exactement le certificat du Site (signé par l'Autorité du Site ou
  fourni par l'Administrateur) : seule cette machine a sa clé.
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

# Change à chaque démarrage : seule cette instance de l'API le connaît.
JETON_INSTANCE = secrets.token_hex(16)
CHEMIN_INSTANCE = "/api/instance"
# Certificat présenté par le Site, monté seul par compose.yaml (sans sa clé) ; chaîne éventuelle à la suite.
CERTIFICAT_DU_SITE = Path("/etc/argos/serveur.crt")
# Nom demandé (SNI, Host) : le Site n'a qu'une origine HTTPS, il répond quel que soit le nom.
NOM_DEMANDE = "localhost"
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
        attendu = _certificat_du_site()
    except (OSError, ValueError):
        return set()
    # Le certificat est comparé à celui du Site, octet pour octet : l'adresse demandée (passerelle Docker,
    # IP d'un Candidat) n'est pas forcément un de ses noms, et api ne connaît pas l'Autorité du Site.
    contexte = ssl.create_default_context()
    contexte.check_hostname = False
    contexte.verify_mode = ssl.CERT_NONE
    with ThreadPoolExecutor(len(ips)) as appels:
        reponses = list(appels.map(lambda ip: _jeton(ip, port_https, contexte, attendu, delai), ips))
    return {ip for ip, jeton in zip(ips, reponses, strict=True) if jeton == JETON_INSTANCE}


def _certificat_du_site() -> bytes:
    """Le certificat du Site (DER), premier de son fichier."""
    pem = CERTIFICAT_DU_SITE.read_text()
    return ssl.PEM_cert_to_DER_cert(pem[: pem.index(_FIN_PEM) + len(_FIN_PEM)].strip())


def _jeton(
    ip: IPv4Address, port_https: int, contexte: ssl.SSLContext, attendu: bytes, delai: float
) -> str | None:
    connexion = http.client.HTTPConnection(str(ip), port_https, timeout=delai)
    try:
        with socket.create_connection((str(ip), port_https), timeout=delai) as brut:
            connexion.sock = contexte.wrap_socket(brut, server_hostname=NOM_DEMANDE)
        if connexion.sock.getpeercert(binary_form=True) != attendu:
            return None
        connexion.request("GET", CHEMIN_INSTANCE, headers={"Host": NOM_DEMANDE})
        return json.load(connexion.getresponse()).get("instance")
    except (OSError, ValueError, AttributeError):
        return None
    finally:
        connexion.close()
