"""Fuseaux de l'Horloge : nom IANA lisible (`Europe/Paris`) ↔ chaîne POSIX qu'attend ONVIF.

La chaîne POSIX envoyée aux Caméras est le décalage du moment du fuseau, sans règles d'heure d'été (`CEST-2` en été,
`CET-1` en hiver) : une caméra qui ne sait pas les appliquer incruste quand même l'heure locale
(docs/adr/0015-mise-a-l-heure-a-chaque-verification.md, avenant). La chaîne POSIX qui clôt le fichier TZif d'un
fuseau (`CET-1CEST,M3.5.0,M10.5.0/3`) décrit ses règles ; elle reconnaît le fuseau de l'hôte.

Règles et décalages viennent de la base des fuseaux de l'hôte quand il en monte une (`/usr/share/zoneinfo`, tenue à
jour par l'OS), sinon du paquet `tzdata` embarqué ; jamais de celle de l'image. Une base qui change de version est
reprise sans redémarrage, à la lecture suivante de `base()` (docs/adr/0015-mise-a-l-heure-a-chaque-verification.md,
second avenant).
"""

import math
import re
import threading
import zoneinfo
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, available_timezones

import tzdata

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


# Nom POSIX envoyé quand l'abréviation du fuseau n'est pas en lettres (`+01`) ou vaut `UTC` / `GMT` : une caméra lit
# `UTC-2` à l'envers.
NOM_NEUTRE = "ARGOS"
# Nom POSIX (en lettres, ou entre chevrons), puis décalage `[+-]hh[:mm[:ss]]` : la suite (heure d'été) est ignorée.
_DEBUT_POSIX = re.compile(r"^(?:[A-Za-z]{3,}|<[A-Za-z0-9+-]{3,}>)([+-]?)(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?")
# Changements d'heure cherchés jusqu'à cet horizon, jour par jour, puis à la seconde.
_HORIZON_CHANGEMENT = timedelta(days=400)


# `hote` : la base montée depuis l'hôte ; `embarquee` : le paquet `tzdata` de l'image, en secours.
Origine = Literal["hote", "embarquee"]


@dataclass(frozen=True)
class BaseDesFuseaux:
    version: str | None
    origine: Origine


_EMBARQUEE = BaseDesFuseaux(version=tzdata.IANA_VERSION, origine="embarquee")
_verrou = threading.Lock()
_dossier_hote: Path | None = None
_base = _EMBARQUEE
# Ni la base de l'image (`/usr/share/zoneinfo` de Debian, figée à sa construction) ni une autre : le paquet `tzdata`.
zoneinfo.reset_tzpath([])


def utiliser_la_base_de_l_hote(dossier: Path | None) -> None:
    """Base des fuseaux de l'hôte, montée en `dossier` ; `None`, ou un dossier sans version : base embarquée."""
    global _dossier_hote
    with _verrou:
        _dossier_hote = dossier
    base()


def base() -> BaseDesFuseaux:
    """Base des fuseaux en usage, relue : si sa version a changé (mise à jour de l'OS), les caches sont vidés et les
    calculs suivants la suivent."""
    global _base
    with _verrou:
        version = _version_de_l_hote(_dossier_hote) if _dossier_hote is not None else None
        lue = _EMBARQUEE if version is None else BaseDesFuseaux(version=version, origine="hote")
        if lue != _base:
            zoneinfo.reset_tzpath([str(_dossier_hote)] if lue.origine == "hote" else [])
            ZoneInfo.clear_cache()
            for calcul in (_noms_iana, posix, _noms_par_posix):
                calcul.cache_clear()
            _base = lue
        return _base


def _version_de_l_hote(dossier: Path) -> str | None:
    """Version de la base `dossier` (`+VERSION`, sinon l'en-tête de `tzdata.zi`) ; `None` : pas de base lisible."""
    try:
        return (dossier / "+VERSION").read_text().strip() or None
    except (OSError, UnicodeDecodeError):
        pass
    try:
        with (dossier / "tzdata.zi").open() as zi:
            entete = zi.readline()
    except (OSError, UnicodeDecodeError):
        return None
    if not entete.startswith("# version"):
        return None
    return entete.removeprefix("# version").strip() or None


def connu(nom: str) -> bool:
    """`nom` est un fuseau IANA de la base (seul cas où `posix` peut le lire)."""
    return nom in _noms_iana()


@cache
def _noms_iana() -> frozenset[str]:
    return frozenset(available_timezones())


@cache
def posix(nom: str) -> str:
    """Chaîne POSIX du fuseau IANA `nom` (ex. `Europe/Paris` → `CET-1CEST,M3.5.0,M10.5.0/3`), lue dans la base de
    l'hôte si elle a ce fuseau, sinon dans la base embarquée (comme `zoneinfo`)."""
    morceaux = nom.split("/")
    if _base.origine == "hote" and _dossier_hote is not None:
        try:
            return _posix_du_tzif(_dossier_hote.joinpath(*morceaux).read_bytes())
        except OSError:
            pass
    return _posix_du_tzif(files("tzdata").joinpath("zoneinfo", *morceaux).read_bytes())


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
    nom = _noms_par_posix().get(chaine) or next((n for n in sorted(_noms_iana()) if _posix_sur(n) == chaine), None)
    return nom or FUSEAU_DE_REPLI


def _posix_sur(nom: str) -> str | None:
    """Chaîne POSIX de `nom`, `None` si son fichier manque à la base."""
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


def nom_lisible(chaine_posix: str, moment: datetime) -> str | None:
    """Fuseau IANA courant de cette chaîne POSIX, envoyée à `moment` ou décrivant ses règles ; `None` : inconnu, à
    montrer tel quel."""
    chaine = chaine_posix.strip()
    du_moment = (nom for nom in FUSEAUX_COURANTS if posix_du_moment(nom, moment) == chaine)
    return _noms_par_posix().get(chaine) or next(du_moment, None)


def posix_du_moment(nom: str, moment: datetime) -> str:
    """Chaîne POSIX sans règles du fuseau IANA `nom` à `moment` : son abréviation et son décalage d'alors
    (`Europe/Paris` → `CEST-2` en été, `CET-1` en hiver ; `NOM_NEUTRE` si l'abréviation est numérique ou UTC / GMT)."""
    local = moment.astimezone(ZoneInfo(nom))
    abreviation = local.tzname() or ""
    if not abreviation.isalpha() or len(abreviation) < 3 or abreviation in ("UTC", "GMT"):
        abreviation = NOM_NEUTRE
    utc = local.utcoffset() or timedelta()
    # POSIX compte à l'envers : UTC+2 s'écrit `-2`.
    signe = "-" if utc > timedelta() else ""
    heures, reste = divmod(int(abs(utc).total_seconds()), 3600)
    minutes, secondes = divmod(reste, 60)
    texte = str(heures) + (f":{minutes:02d}" if minutes or secondes else "") + (f":{secondes:02d}" if secondes else "")
    return f"{abreviation}{signe}{texte}"


def decalage(chaine_posix: str) -> timedelta | None:
    """Décalage UTC de l'heure normale d'une chaîne POSIX (`CEST-2` → +2 h), règles et nom d'heure d'été ignorés,
    comme une caméra qui ne les applique pas ; `None` : illisible."""
    lu = _DEBUT_POSIX.match(chaine_posix.strip())
    if lu is None:
        return None
    signe, heures, minutes, secondes = lu.groups()
    ouest = timedelta(hours=int(heures), minutes=int(minutes or 0), seconds=int(secondes or 0))
    return ouest if signe == "-" else -ouest


def prochain_changement(nom: str, apres: datetime) -> datetime | None:
    """Prochain instant, strictement après `apres`, où le décalage du fuseau IANA `nom` change ; `None` s'il n'en
    prévoit pas dans l'année. Cherché jour par jour, puis à la seconde (un changement tombe sur une seconde ronde)."""
    zone = ZoneInfo(nom)

    def decalage_a(seconde: int) -> timedelta | None:
        return datetime.fromtimestamp(seconde, zone).utcoffset()

    avant = math.floor(apres.timestamp())
    actuel = decalage_a(avant)
    jour = int(timedelta(days=1).total_seconds())
    for fin in range(avant + jour, avant + int(_HORIZON_CHANGEMENT.total_seconds()) + jour, jour):
        if decalage_a(fin) != actuel:
            # `avant` garde le décalage actuel, `fin` a le nouveau.
            while fin - avant > 1:
                milieu = (avant + fin) // 2
                if decalage_a(milieu) == actuel:
                    avant = milieu
                else:
                    fin = milieu
            return datetime.fromtimestamp(fin, UTC)
        avant = fin
    return None
