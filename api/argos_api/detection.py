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
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network

# Sondes simultanées : un /24 sur deux ports (508 sondes) tient en quelques tours de délai.
CONCURRENCE = 128
STATUT_RTSP = re.compile(rb"^RTSP/\d\.\d (\d{3})")
SERVEUR = re.compile(rb"^server:[ \t]*(.*?)[ \t]*\r?$", re.IGNORECASE | re.MULTILINE)
# Ligne de statut puis en-têtes : une réponse à OPTIONS tient largement dedans.
TAILLE_ENTETES_MAX = 4096


@dataclass(frozen=True, order=True)
class Cible:
    ip: IPv4Address
    port: int


@dataclass(frozen=True, order=True)
class Candidat(Cible):
    """Diagnostic en plus de l'adresse : statut de la réponse à `OPTIONS` et en-tête `Server` annoncé."""

    statut_rtsp: int = field(compare=False)
    serveur: str | None = field(compare=False)


def detecter(
    sous_reseaux: Iterable[IPv4Network], ports: Sequence[int], exclues: Collection[IPv4Address], delai: float
) -> list[Candidat]:
    """Candidats des sous-réseaux, triés par IP puis port ; `delai` borne chaque sonde, en secondes."""
    cibles = sorted({
        Cible(ip, port)
        for reseau in sous_reseaux
        for ip in reseau.hosts()
        if ip not in exclues
        for port in ports
    })
    with ThreadPoolExecutor(CONCURRENCE) as sondes:
        candidats = list(sondes.map(lambda cible: interroger(cible, delai), cibles))
    return [candidat for candidat in candidats if candidat is not None]


def interroger(cible: Cible, delai: float) -> Candidat | None:
    """La cible comme Candidat si elle répond en RTSP à `OPTIONS` dans `delai` secondes ; `None` sinon."""
    echeance = time.monotonic() + delai
    try:
        with socket.create_connection((str(cible.ip), cible.port), timeout=delai) as connexion:
            requete = f"OPTIONS rtsp://{cible.ip}:{cible.port} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: ArgOS\r\n\r\n"
            connexion.sendall(requete.encode())
            entetes = _entetes(connexion, echeance)
    except OSError:
        return None
    statut = STATUT_RTSP.match(entetes)
    if statut is None:
        return None
    serveur = SERVEUR.search(entetes.partition(b"\r\n\r\n")[0])
    return Candidat(
        cible.ip,
        cible.port,
        int(statut.group(1)),
        serveur.group(1).decode(errors="replace") if serveur else None,
    )


def _entetes(connexion: socket.socket, echeance: float) -> bytes:
    """Ligne de statut et en-têtes ; une réponse tronquée (délai, fermeture, taille) garde ce qui est arrivé."""
    recu = b""
    while b"\r\n\r\n" not in recu and len(recu) < TAILLE_ENTETES_MAX:
        restant = echeance - time.monotonic()
        if restant <= 0:
            break
        connexion.settimeout(restant)
        try:
            morceau = connexion.recv(TAILLE_ENTETES_MAX)
        except TimeoutError:
            break
        if not morceau:
            break
        recu += morceau
    return recu
