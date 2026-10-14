"""ArgOS lui-même, jamais Candidat d'une Détection.

Deux façons de le reconnaître, sans rien savoir de la simulation :
- ses conteneurs : les adresses de `api` et celles du pont (résolues par son nom Compose) ;
- toute machine qui publie cette API (l'hôte du Site, vu par son adresse locale ou par la passerelle
  d'un réseau Docker) : elle publie aussi le pont, et renvoie le jeton de cette instance sur l'origine
  HTTPS du Site (ADR 0005), dont le certificat est vérifié contre l'Autorité du Site.
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
# Partie publique de l'Autorité du Site, montée seule par compose.yaml (ni la clé de l'Autorité, ni celle du serveur).
AUTORITE_DU_SITE = Path("/etc/argos/argos-ca.crt")
# Nom que porte tout certificat serveur signé par l'Autorité : l'adresse demandée (passerelle Docker,
# IP d'un Candidat) n'en est pas forcément un.
NOM_DU_SITE = "localhost"


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

    Sans Autorité du Site lisible, aucune : le certificat présenté ne peut pas être vérifié.
    """
    ips = sorted(set(ips))
    if not ips:
        return set()
    try:
        contexte = ssl.create_default_context(cafile=AUTORITE_DU_SITE)
    except OSError:
        return set()
    with ThreadPoolExecutor(len(ips)) as appels:
        reponses = list(appels.map(lambda ip: _jeton(ip, port_https, contexte, delai), ips))
    return {ip for ip, jeton in zip(ips, reponses, strict=True) if jeton == JETON_INSTANCE}


def _jeton(ip: IPv4Address, port_https: int, contexte: ssl.SSLContext, delai: float) -> str | None:
    connexion = http.client.HTTPConnection(str(ip), port_https, timeout=delai)
    try:
        with socket.create_connection((str(ip), port_https), timeout=delai) as brut:
            connexion.sock = contexte.wrap_socket(brut, server_hostname=NOM_DU_SITE)
        connexion.request("GET", CHEMIN_INSTANCE, headers={"Host": NOM_DU_SITE})
        return json.load(connexion.getresponse()).get("instance")
    except (OSError, ValueError, AttributeError):
        return None
    finally:
        connexion.close()
