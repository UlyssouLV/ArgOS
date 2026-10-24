"""Serveur de temps du Site (`temps`, docs/adr/0014-serveur-de-temps-du-site.md), vu de l'API : la source qu'il doit
suivre, transmise par un fichier du volume qu'ils partagent ; ce qu'il sert vraiment, lu en NTP comme une Caméra ;
l'heure qu'il sert, référence de la Mise à l'heure (docs/adr/0015-mise-a-l-heure-a-chaque-verification.md) ;
l'adresse annoncée aux Caméras.

Sans dépendance hors stdlib : testé seul (tests/api/test_serveur_de_temps.py).
"""

import os
import socket
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal

PORT_NTP = 123
DELAI_S = 1.0
# Identifiant de référence de chrony en `local stratum 10` (temps/lancer.sh) : il sert l'horloge du serveur. La
# strate seule ne suffit pas : une source amont en strate 9 donne aussi la strate 10.
REFERENCE_DU_REPLI = "127.127.1.1"
# Indicateur de seconde intercalaire 3 : horloge non synchronisée (RFC 5905).
NON_SYNCHRONISE = 3
# Secondes entre l'époque NTP (1900) et l'époque Unix (1970).
EPOQUE_NTP = 2_208_988_800
# Lu par temps/lancer.sh, dans le volume partagé.
FICHIER_SOURCE = "source"

# `ntp` : temps suit une source externe ; `horloge_serveur` : l'horloge du serveur (choisie, ou repli d'une source
# injoignable) ; `non_synchronise` : temps démarre ; `injoignable` : temps ne répond pas.
SourceUtilisee = Literal["ntp", "horloge_serveur", "non_synchronise", "injoignable"]


@dataclass(frozen=True)
class EtatServi:
    source_utilisee: SourceUtilisee
    # Adresse du serveur que temps suit (identifiant de référence NTP), seulement en `ntp`.
    reference: str | None = None
    # Heure UTC servie aux Caméras.
    heure: datetime | None = None


def transmettre(dossier: Path, serveur_ntp: str | None) -> None:
    """Écrit la source que `temps` doit suivre : `serveur_ntp`, ou `None` pour l'horloge du serveur.

    Renommé d'un bloc : temps ne lit jamais un fichier à moitié écrit.
    """
    temporaire = dossier / f".{FICHIER_SOURCE}"
    temporaire.write_text(f"{serveur_ntp or ''}\n")
    os.replace(temporaire, dossier / FICHIER_SOURCE)


def interroger(hote: str, port: int = PORT_NTP, delai_s: float = DELAI_S) -> EtatServi:
    """Une requête NTP client (version 4, mode 3) à `temps` : ce qu'il sert aux Caméras."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as prise:
            prise.settimeout(delai_s)
            prise.sendto(b"\x23" + bytes(47), (hote, port))
            paquet, _ = prise.recvfrom(512)
    except OSError:
        return EtatServi("injoignable")
    if len(paquet) < 48:
        return EtatServi("injoignable")
    secondes, fraction = struct.unpack("!II", paquet[40:48])
    heure = datetime.fromtimestamp(secondes - EPOQUE_NTP + fraction / 2**32, UTC)
    strate = paquet[1]
    if paquet[0] >> 6 == NON_SYNCHRONISE or not 0 < strate < 16:
        return EtatServi("non_synchronise", heure=heure)
    # Source IPv4 : son adresse ; IPv6 : une empreinte, lue de même.
    reference = socket.inet_ntoa(paquet[12:16])
    if reference == REFERENCE_DU_REPLI:
        return EtatServi("horloge_serveur", heure=heure)
    return EtatServi("ntp", reference, heure)


def horloge_servie(hote: str, port: int = PORT_NTP, delai_s: float = DELAI_S) -> Callable[[], datetime] | None:
    """Heure UTC que sert `temps`, lue une fois en NTP puis avancée sur l'horloge monotone de l'API (jamais sur
    l'heure de son OS) ; `None` : temps ne répond pas."""
    avant = time.monotonic()
    heure = interroger(hote, port, delai_s).heure
    if heure is None:
        return None
    # Heure émise par temps à mi-chemin de l'aller-retour.
    lue_a = (avant + time.monotonic()) / 2
    return lambda: heure + timedelta(seconds=time.monotonic() - lue_a)


def adresse_annoncee(ip_temps: str, ips_du_site: str) -> str | None:
    """IP de `temps` sur le réseau des caméras si elle est donnée, sinon la première IPv4 du Site (`ips_du_site`,
    séparées par des virgules) ; `None` : aucune, le Site ne peut pas caler les Caméras."""
    for candidate in (ip_temps, *ips_du_site.split(",")):
        try:
            return str(IPv4Address(candidate.strip()))
        except ValueError:
            continue
    return None
