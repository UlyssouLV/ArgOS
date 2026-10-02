"""Détection : cherche dans des sous-réseaux les hôtes qui peuvent devenir des Caméras.

Candidat : connexion TCP acceptée sur un port caméra, puis réponse à `OPTIONS` (sans chemin ni
identifiants) qui commence par une ligne de statut RTSP, quel que soit le statut. Port ouvert sans
réponse RTSP : pas un Candidat. Rien d'autre n'est envoyé (docs/securite.md).
"""

import re
import socket
import time
from collections.abc import Collection, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

# Sondes simultanées : un /24 sur deux ports (508 sondes) tient en quelques tours de délai.
CONCURRENCE = 128
STATUT_RTSP = re.compile(rb"^RTSP/\d\.\d \d{3}")
TAILLE_LIGNE_MAX = 256


@dataclass(frozen=True, order=True)
class Candidat:
    ip: IPv4Address
    port: int


def detecter(
    sous_reseaux: Iterable[IPv4Network], ports: Sequence[int], exclues: Collection[IPv4Address], delai: float
) -> list[Candidat]:
    """Candidats des sous-réseaux, triés par IP puis port ; `delai` borne chaque sonde, en secondes."""
    cibles = sorted({
        Candidat(ip, port)
        for reseau in sous_reseaux
        for ip in reseau.hosts()
        if ip not in exclues
        for port in ports
    })
    with ThreadPoolExecutor(CONCURRENCE) as sondes:
        repondent = list(sondes.map(lambda cible: _repond_en_rtsp(cible, delai), cibles))
    return [cible for cible, repond in zip(cibles, repondent, strict=True) if repond]


def _repond_en_rtsp(cible: Candidat, delai: float) -> bool:
    echeance = time.monotonic() + delai
    try:
        with socket.create_connection((str(cible.ip), cible.port), timeout=delai) as connexion:
            requete = f"OPTIONS rtsp://{cible.ip}:{cible.port} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: ArgOS\r\n\r\n"
            connexion.sendall(requete.encode())
            return STATUT_RTSP.match(_premiere_ligne(connexion, echeance)) is not None
    except OSError:
        return False


def _premiere_ligne(connexion: socket.socket, echeance: float) -> bytes:
    recu = b""
    while b"\r\n" not in recu and len(recu) < TAILLE_LIGNE_MAX:
        restant = echeance - time.monotonic()
        if restant <= 0:
            raise TimeoutError
        connexion.settimeout(restant)
        morceau = connexion.recv(TAILLE_LIGNE_MAX)
        if not morceau:
            break
        recu += morceau
    return recu
