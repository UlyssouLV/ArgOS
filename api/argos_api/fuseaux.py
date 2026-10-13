"""Fuseaux de l'Horloge : nom IANA lisible (`Europe/Paris`) ↔ chaîne POSIX qu'attend ONVIF (`CET-1CEST,…`).

La chaîne POSIX d'un fuseau est celle qui clôt son fichier TZif (paquet `tzdata`) : elle décrit ses règles
actuelles, celles qu'une caméra applique.
"""

from functools import cache
from importlib.resources import files

# Zones courantes, Europe/Paris en tête. Plusieurs zones partagent une même chaîne POSIX : la lecture rend la
# première de cette liste. Hors liste (ex. `AWST-8`, Australie), un fuseau est montré tel quel.
FUSEAUX_COURANTS = (
    "Europe/Paris",
    "UTC",
    "Europe/London",
    "Europe/Lisbon",
    "Europe/Athens",
    "Europe/Moscow",
    "Africa/Casablanca",
    "Africa/Abidjan",
    "America/Guadeloupe",
    "America/Cayenne",
    "America/Miquelon",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Indian/Reunion",
    "Indian/Mayotte",
    "Asia/Dubai",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Pacific/Noumea",
    "Pacific/Tahiti",
    "Pacific/Wallis",
)


@cache
def posix(nom: str) -> str:
    """Chaîne POSIX du fuseau IANA `nom` (ex. `Europe/Paris` → `CET-1CEST,M3.5.0,M10.5.0/3`)."""
    tzif = files("tzdata").joinpath("zoneinfo", *nom.split("/")).read_bytes()
    return tzif.rstrip(b"\n").rpartition(b"\n")[2].decode()


@cache
def _noms_par_posix() -> dict[str, str]:
    noms: dict[str, str] = {}
    for nom in FUSEAUX_COURANTS:
        noms.setdefault(posix(nom), nom)
    return noms


def nom_lisible(chaine_posix: str) -> str | None:
    """Fuseau IANA courant de cette chaîne POSIX ; `None` : inconnu, à montrer tel quel."""
    return _noms_par_posix().get(chaine_posix.strip())
