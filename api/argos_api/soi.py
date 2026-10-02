"""ArgOS lui-même, jamais Candidat d'une Détection.

Deux façons de le reconnaître, sans rien savoir de la simulation :
- ses conteneurs : les adresses de `api` et celles du pont (résolues par son nom Compose) ;
- toute machine qui publie cette API (l'hôte du Site, vu par son adresse locale ou par la passerelle
  d'un réseau Docker) : elle publie aussi le pont, et renvoie le jeton de cette instance.
"""

import json
import secrets
import socket
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from ipaddress import IPv4Address

# Change à chaque démarrage : seule cette instance de l'API le connaît.
JETON_INSTANCE = secrets.token_hex(16)
# Port de l'API, dans son conteneur et publié par compose.yaml.
PORT_API = 8000
CHEMIN_INSTANCE = "/api/instance"


def adresses_des_conteneurs(hotes: Iterable[str]) -> set[IPv4Address]:
    """Adresses IPv4 de ce conteneur et des `hotes` (noms Compose) ; un nom introuvable est ignoré."""
    adresses = set(socket.gethostbyname_ex(socket.gethostname())[2])
    for hote in hotes:
        try:
            adresses |= {info[4][0] for info in socket.getaddrinfo(hote, None, socket.AF_INET)}
        except OSError:
            continue
    return {IPv4Address(adresse) for adresse in adresses}


def publient_cette_api(ips: Iterable[IPv4Address], delai: float) -> set[IPv4Address]:
    """Celles des `ips` qui répondent, sur le port de l'API, le jeton de cette instance."""
    ips = sorted(set(ips))
    if not ips:
        return set()
    with ThreadPoolExecutor(len(ips)) as appels:
        reponses = list(appels.map(lambda ip: _jeton(ip, delai), ips))
    return {ip for ip, jeton in zip(ips, reponses, strict=True) if jeton == JETON_INSTANCE}


def _jeton(ip: IPv4Address, delai: float) -> str | None:
    # HTTP en clair : le jeton n'est pas un secret, seulement l'identité de cette instance.
    url = f"http://{ip}:{PORT_API}{CHEMIN_INSTANCE}"  # NOSONAR
    try:
        with urllib.request.urlopen(url, timeout=delai) as reponse:  # noqa: S310 (schéma fixé ci-dessus)
            return json.load(reponse).get("instance")
    except (OSError, ValueError, AttributeError):
        return None
