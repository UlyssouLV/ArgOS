"""Voisinage : MAC de l'Appareil derrière une IP, lue dans la table de voisinage (ARP) du conteneur.

La table n'a d'entrée que pour un voisin direct à qui ArgOS vient de parler : à lire juste après une
sonde réussie. Derrière un NAT ou un routeur, aucune MAC (docs/adr/0003-macvlan-sur-la-prise-des-cameras.md).
"""

import re
from ipaddress import IPv4Address
from pathlib import Path

TABLE_VOISINAGE = Path("/proc/net/arp")
# Drapeau ATF_COM : entrée complète (MAC résolue).
ENTREE_COMPLETE = 0x2
# Six octets séparés par `:` ou `-`, trois groupes de quatre chiffres séparés par `.`, ou douze chiffres.
_FORMATS = re.compile(
    r"[0-9a-f]{2}([:-])[0-9a-f]{2}(?:\1[0-9a-f]{2}){4}|[0-9a-f]{4}(?:\.[0-9a-f]{4}){2}|[0-9a-f]{12}"
)


def normaliser(saisie: str) -> str:
    """MAC au format `aa:bb:cc:dd:ee:ff`, quel que soit le format de l'étiquette ; `ValueError` sinon."""
    mac = saisie.strip().lower()
    if not _FORMATS.fullmatch(mac):
        raise ValueError(f"MAC invalide : {saisie!r}")
    chiffres = re.sub(r"[:.-]", "", mac)
    return ":".join(chiffres[i : i + 2] for i in range(0, 12, 2))


def mac_de(ip: IPv4Address, table: Path = TABLE_VOISINAGE) -> str | None:
    """MAC normalisée de `ip` si la table en a une entrée complète ; `None` sinon, sans lever."""
    try:
        lignes = table.read_text().splitlines()[1:]
    except OSError:
        return None
    for ligne in lignes:
        champs = ligne.split()
        if len(champs) < 4 or champs[0] != str(ip):
            continue
        try:
            if int(champs[2], 16) & ENTREE_COMPLETE:
                return normaliser(champs[3])
        except ValueError:
            continue
    return None
