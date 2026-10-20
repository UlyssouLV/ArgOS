"""Fuseaux de l'Horloge : nom IANA lisible (`Europe/Paris`) ↔ chaîne POSIX qu'attend ONVIF (`CET-1CEST,…`).

La chaîne POSIX d'un fuseau est celle qui clôt son fichier TZif (paquet `tzdata`) : elle décrit ses règles
actuelles, celles qu'une caméra applique.
"""

from functools import cache
from importlib.resources import files
from pathlib import Path
from zoneinfo import available_timezones

# Fuseau du Site quand celui de l'hôte est illisible.
FUSEAU_DE_REPLI = "UTC"

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


def connu(nom: str) -> bool:
    """`nom` est un fuseau IANA du paquet `tzdata` (seul cas où `posix` peut le lire)."""
    return nom in _noms_iana()


@cache
def _noms_iana() -> frozenset[str]:
    return frozenset(available_timezones())


@cache
def posix(nom: str) -> str:
    """Chaîne POSIX du fuseau IANA `nom` (ex. `Europe/Paris` → `CET-1CEST,M3.5.0,M10.5.0/3`)."""
    return _posix_du_tzif(files("tzdata").joinpath("zoneinfo", *nom.split("/")).read_bytes())


def _posix_du_tzif(tzif: bytes) -> str:
    return tzif.rstrip(b"\n").rpartition(b"\n")[2].decode(errors="replace")


def de_l_hote(localtime: Path) -> str:
    """Fuseau IANA de l'hôte, d'après son `/etc/localtime` monté (le contenu, pas le nom : Docker suit le lien).

    Reconnu par ses règles actuelles (chaîne POSIX) : le premier des fuseaux courants qui les partage, sinon le
    premier fuseau IANA par ordre alphabétique ; illisible ou inconnu : `FUSEAU_DE_REPLI`.
    """
    try:
        chaine = _posix_du_tzif(localtime.read_bytes())
    except OSError:
        return FUSEAU_DE_REPLI
    nom = nom_lisible(chaine) or next((n for n in sorted(_noms_iana()) if _posix_sur(n) == chaine), None)
    return nom or FUSEAU_DE_REPLI


def _posix_sur(nom: str) -> str | None:
    """Chaîne POSIX de `nom`, `None` si son fichier manque au paquet `tzdata`."""
    try:
        return posix(nom)
    except (OSError, ValueError):
        return None


@cache
def _noms_par_posix() -> dict[str, str]:
    noms: dict[str, str] = {}
    for nom in FUSEAUX_COURANTS:
        noms.setdefault(posix(nom), nom)
    return noms


def nom_lisible(chaine_posix: str) -> str | None:
    """Fuseau IANA courant de cette chaîne POSIX ; `None` : inconnu, à montrer tel quel."""
    return _noms_par_posix().get(chaine_posix.strip())
