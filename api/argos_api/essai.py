"""Essai d'un Candidat : ArgOS cherche seul son Flux, sur les chemins courants des caméras.

`OPTIONS` d'abord : sans réponse RTSP, l'hôte est injoignable ; son en-tête `Server` fait passer en tête
les chemins d'une marque reconnue. Puis `DESCRIBE` sur chaque chemin jusqu'au premier `200`, confirmé
par la sonde (au moins un paquet vidéo). Un `401` arrête l'essai : la plupart des caméras le répondent
avant de vérifier le chemin, et un seul essai d'identifiants est fait par demande.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from ipaddress import IPv4Address
from urllib.parse import quote

from argos_api import detection, sonde


class Issue(StrEnum):
    FLUX_TROUVE = "flux_trouve"
    IDENTIFIANTS_REQUIS = "identifiants_requis"
    IDENTIFIANTS_REFUSES = "identifiants_refuses"
    FLUX_INTROUVABLE = "flux_introuvable"
    INJOIGNABLE = "injoignable"


@dataclass(frozen=True)
class CheminsMarque:
    # Reconnue quand l'en-tête `Server` la contient (sans casse) ; `None` : chemins génériques.
    marque: str | None
    principal: str
    secondaire: str | None


# Flux principal (meilleure qualité) avant flux secondaire, chaque fois que la caméra offre les deux.
CHEMINS_COURANTS: Sequence[CheminsMarque] = (
    CheminsMarque("hikvision", "/Streaming/Channels/101", "/Streaming/Channels/102"),
    CheminsMarque("dahua", "/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor?channel=1&subtype=1"),
    CheminsMarque("reolink", "/h264Preview_01_main", "/h264Preview_01_sub"),
    CheminsMarque("uniview", "/media/video1", "/media/video2"),
    CheminsMarque("axis", "/axis-media/media.amp", None),
    CheminsMarque(None, "/stream1", "/stream2"),
    CheminsMarque(None, "/11", "/12"),
    CheminsMarque(None, "/live/ch00_0", "/live/ch00_1"),
)


@dataclass(frozen=True)
class Resultat:
    issue: Issue
    chemin: str | None = None
    # Nom d'encodage lu dans le SDP (`H264`, `H265`…).
    codec: str | None = None
    # Identifiants compris : ni renvoyée au navigateur, ni journalisée.
    url: str | None = field(default=None, repr=False)


def essayer(
    ip: IPv4Address,
    port: int,
    delai: float,
    identifiant: str | None = None,
    mot_de_passe: str | None = None,
    chemin: str | None = None,
) -> Resultat:
    """`chemin` saisi : seul essayé. `delai` borne chaque échange avec la caméra, en secondes."""
    candidat = detection.interroger(detection.Cible(ip, port), delai)
    if candidat is None:
        return Resultat(Issue.INJOIGNABLE)
    for essaye in [_normaliser(chemin)] if chemin else chemins_ordonnes(candidat.serveur):
        url = url_flux(ip, port, essaye, identifiant, mot_de_passe)
        description = sonde.decrire(url, delai)
        if description is None:
            continue
        if description.statut == 401:
            return Resultat(Issue.IDENTIFIANTS_REFUSES if identifiant else Issue.IDENTIFIANTS_REQUIS)
        if description.statut == 200 and sonde.sonder(url, delai):
            return Resultat(Issue.FLUX_TROUVE, essaye, description.codec, url)
    return Resultat(Issue.FLUX_INTROUVABLE)


def chemins_ordonnes(serveur: str | None) -> list[str]:
    """Chemins courants, ceux de la marque reconnue dans `serveur` en tête ; principaux avant secondaires."""
    serveur = (serveur or "").lower()
    reconnues = [c for c in CHEMINS_COURANTS if c.marque and c.marque in serveur]
    autres = [c for c in CHEMINS_COURANTS if c not in reconnues]
    return [
        chemin
        for groupe in (reconnues, autres)
        for chemin in [c.principal for c in groupe] + [c.secondaire for c in groupe if c.secondaire]
    ]


def url_flux(ip: IPv4Address, port: int, chemin: str, identifiant: str | None, mot_de_passe: str | None) -> str:
    """`rtsp://identifiant:motdepasse@ip:port/chemin`, caractères spéciaux des identifiants encodés."""
    acces = f"{quote(identifiant, safe='')}:{quote(mot_de_passe or '', safe='')}@" if identifiant else ""
    return f"rtsp://{acces}{ip}:{port}{_normaliser(chemin)}"


def _normaliser(chemin: str) -> str:
    return "/" + chemin.strip().lstrip("/")
