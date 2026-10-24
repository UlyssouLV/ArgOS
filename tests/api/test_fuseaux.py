"""Fuseau envoyé aux Caméras et vérification au changement d'heure (tests unitaires,
docs/adr/0015-mise-a-l-heure-a-chaque-verification.md, avenant).

Le Site envoie le décalage horaire du moment de son fuseau, sans règles d'heure d'été : une caméra qui ne sait pas
appliquer l'heure d'été incruste quand même l'heure locale du Site. Il vérifie toutes les Caméras à l'instant de
chaque changement d'heure, joué ici avec une horloge simulée.
"""

import re
import threading
import time
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from zoneinfo import ZoneInfo

import pytest
import tzdata

from argos_api import fuseaux
from argos_api.changement_d_heure import VerificationAuChangementDHeure

ETE = datetime(2026, 7, 15, 12, tzinfo=UTC)
HIVER = datetime(2026, 1, 15, 12, tzinfo=UTC)
# Un nom POSIX en lettres (au moins 3), un décalage, rien d'autre : pas de nom ni de règles d'heure d'été.
POSIX_SANS_REGLES = re.compile(r"^[A-Za-z]{3,}[+-]?\d{1,2}(:\d{2}){0,2}$")


@pytest.mark.parametrize("moment", [ETE, HIVER], ids=["ete", "hiver"])
@pytest.mark.parametrize("nom", fuseaux.FUSEAUX_COURANTS)
def test_fuseau_envoye_sans_regles_au_decalage_du_moment(nom, moment):
    envoye = fuseaux.posix_du_moment(nom, moment)

    assert POSIX_SANS_REGLES.match(envoye), envoye
    assert not envoye.startswith(("UTC", "GMT")), envoye
    assert fuseaux.decalage(envoye) == moment.astimezone(ZoneInfo(nom)).utcoffset()


@pytest.mark.parametrize(
    ("nom", "moment", "envoye"),
    [
        ("Europe/Paris", ETE, "CEST-2"),
        ("Europe/Paris", HIVER, "CET-1"),
        ("America/New_York", ETE, "EDT4"),
        ("America/New_York", HIVER, "EST5"),
        ("UTC", ETE, f"{fuseaux.NOM_NEUTRE}0"),
        ("Africa/Abidjan", HIVER, f"{fuseaux.NOM_NEUTRE}0"),
        ("Africa/Casablanca", HIVER, f"{fuseaux.NOM_NEUTRE}-1"),
        ("America/Cayenne", ETE, f"{fuseaux.NOM_NEUTRE}3"),
    ],
)
def test_fuseau_envoye_abreviation_ou_nom_neutre(nom, moment, envoye):
    assert fuseaux.posix_du_moment(nom, moment) == envoye


@pytest.mark.parametrize(
    ("relu", "decalage"),
    [
        ("CEST-2", timedelta(hours=2)),
        # Ce que garde la vraie caméra des tests humains : le décalage, avec ou sans nom d'heure d'été.
        ("EET-2EETDST", timedelta(hours=2)),
        ("CET-1CEST", timedelta(hours=1)),
        ("CET-1CEST,M3.5.0,M10.5.0/3", timedelta(hours=1)),
        ("FNT2", timedelta(hours=-2)),
        ("<+0530>-5:30", timedelta(hours=5, minutes=30)),
        ("EST+5", timedelta(hours=-5)),
        ("AWST-8", timedelta(hours=8)),
    ],
)
def test_decalage_d_un_fuseau_posix_relu(relu, decalage):
    assert fuseaux.decalage(relu) == decalage


@pytest.mark.parametrize("relu", ["", "UTC", "n'importe quoi", "Europe/Paris"])
def test_decalage_illisible(relu):
    assert fuseaux.decalage(relu) is None


def test_fuseau_relu_au_decalage_du_moment_reconnu():
    assert fuseaux.nom_lisible("CEST-2", ETE) == "Europe/Paris"
    assert fuseaux.nom_lisible("CET-1", HIVER) == "Europe/Paris"
    assert fuseaux.nom_lisible(f"{fuseaux.NOM_NEUTRE}-11", ETE) == "Pacific/Noumea"
    assert fuseaux.nom_lisible(fuseaux.posix("Europe/Paris"), ETE) == "Europe/Paris"
    assert fuseaux.nom_lisible("AWST-8", ETE) is None


@pytest.mark.parametrize(
    ("nom", "apres", "changement"),
    [
        ("Europe/Paris", datetime(2026, 10, 23, tzinfo=UTC), datetime(2026, 10, 25, 1, tzinfo=UTC)),
        ("Europe/Paris", datetime(2026, 10, 25, 1, tzinfo=UTC), datetime(2027, 3, 28, 1, tzinfo=UTC)),
        ("America/New_York", datetime(2026, 10, 23, tzinfo=UTC), datetime(2026, 11, 1, 6, tzinfo=UTC)),
        ("UTC", datetime(2026, 10, 23, tzinfo=UTC), None),
        ("Asia/Tokyo", datetime(2026, 10, 23, tzinfo=UTC), None),
    ],
)
def test_prochain_changement_d_heure(nom, apres, changement):
    assert fuseaux.prochain_changement(nom, apres) == changement


class HorlogeSimulee:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def attendre(condition, delai_s: float = 5) -> None:
    fin = time.monotonic() + delai_s
    while not condition():
        assert time.monotonic() < fin
        time.sleep(0.01)


@pytest.fixture
def au_changement_d_heure():
    """Vérification au changement d'heure du fuseau `fuseau["nom"]`, à l'horloge simulée `horloge` ; `verifiees` compte
    les vérifications de toutes les Caméras actives."""
    horloge = HorlogeSimulee(datetime(2026, 10, 25, 0, 59, 59, tzinfo=UTC))
    fuseau = {"nom": "Europe/Paris"}
    verifiees: list[datetime] = []
    verrou = threading.Lock()

    def verifier_toutes() -> None:
        with verrou:
            verifiees.append(horloge())

    programme = VerificationAuChangementDHeure(lambda: fuseau["nom"], horloge, verifier_toutes, pas_s=0.01)
    programme.demarrer()
    yield programme, horloge, fuseau, verifiees
    programme.arreter()


def test_verification_a_l_instant_du_changement_d_heure_puis_reprogrammee(au_changement_d_heure):
    programme, horloge, _, verifiees = au_changement_d_heure
    attendre(lambda: programme.prevue == datetime(2026, 10, 25, 1, tzinfo=UTC))
    time.sleep(0.05)
    assert verifiees == []

    horloge.moment = datetime(2026, 10, 25, 1, tzinfo=UTC)

    attendre(lambda: programme.prevue == datetime(2027, 3, 28, 1, tzinfo=UTC))
    assert verifiees == [datetime(2026, 10, 25, 1, tzinfo=UTC)]


def test_verification_reprogrammee_au_changement_de_fuseau(au_changement_d_heure):
    programme, _, fuseau, verifiees = au_changement_d_heure
    attendre(lambda: programme.prevue == datetime(2026, 10, 25, 1, tzinfo=UTC))

    fuseau["nom"] = "America/New_York"
    programme.reprogrammer()
    attendre(lambda: programme.prevue == datetime(2026, 11, 1, 6, tzinfo=UTC))

    fuseau["nom"] = "UTC"
    programme.reprogrammer()
    attendre(lambda: programme.prevue is None)
    assert verifiees == []


def test_instant_recalcule_apres_un_fuseau_illisible():
    """Base indisponible au démarrage : l'instant est recalculé au pas suivant, sans attendre un changement de
    fuseau."""
    horloge = HorlogeSimulee(datetime(2026, 10, 25, 0, 59, 59, tzinfo=UTC))
    lectures = []

    def fuseau() -> str:
        lectures.append(horloge())
        if len(lectures) == 1:
            raise ConnectionError("base indisponible")
        return "Europe/Paris"

    programme = VerificationAuChangementDHeure(fuseau, horloge, lambda: None, pas_s=0.01)
    programme.demarrer()
    try:
        attendre(lambda: programme.prevue == datetime(2026, 10, 25, 1, tzinfo=UTC))
    finally:
        programme.arreter()


@pytest.fixture
def base_de_l_hote(tmp_path):
    """Base des fuseaux de l'hôte, montée dans `api` : ici `Africa/Casablanca` y suit les règles d'`Europe/Paris`
    (UTC+1, heure d'été), là où la base embarquée le met à UTC+0 ou UTC+1 sans changement d'heure en octobre."""
    (tmp_path / "+VERSION").write_text("2099a\n")
    poser(tmp_path, "Africa/Casablanca", "Europe/Paris")
    fuseaux.utiliser_la_base_de_l_hote(tmp_path)
    yield tmp_path
    fuseaux.utiliser_la_base_de_l_hote(None)


def poser(dossier, nom: str, regles: str) -> None:
    """`nom` suit, dans la base `dossier`, les règles du fuseau `regles` de la base embarquée."""
    fichier = dossier.joinpath(*nom.split("/"))
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(files("tzdata").joinpath("zoneinfo", *regles.split("/")).read_bytes())


def test_decalage_et_changement_d_heure_pris_dans_la_base_de_l_hote(base_de_l_hote):
    assert fuseaux.base() == fuseaux.BaseDesFuseaux(version="2099a", origine="hote")
    assert fuseaux.posix_du_moment("Africa/Casablanca", ETE) == "CEST-2"
    assert fuseaux.prochain_changement("Africa/Casablanca", datetime(2026, 10, 23, tzinfo=UTC)) == datetime(
        2026, 10, 25, 1, tzinfo=UTC
    )
    # Ce que la base de l'hôte n'a pas reste lu dans la base embarquée.
    assert fuseaux.posix_du_moment("America/New_York", ETE) == "EDT4"


def test_version_lue_dans_tzdata_zi_sans_plus_version(base_de_l_hote):
    (base_de_l_hote / "+VERSION").unlink()
    (base_de_l_hote / "tzdata.zi").write_text("# version 2099b\n# redo posix_only\n")

    assert fuseaux.base() == fuseaux.BaseDesFuseaux(version="2099b", origine="hote")


@pytest.mark.parametrize("dossier", [None, "vide", "absent"])
def test_sans_base_de_l_hote_la_base_embarquee_sert(tmp_path, dossier):
    """Hôte sans base : Docker crée un dossier vide à la place du montage."""
    fuseaux.utiliser_la_base_de_l_hote({None: None, "vide": tmp_path, "absent": tmp_path / "absent"}[dossier])
    try:
        assert fuseaux.base() == fuseaux.BaseDesFuseaux(version=tzdata.IANA_VERSION, origine="embarquee")
        assert fuseaux.posix_du_moment("Europe/Paris", ETE) == "CEST-2"
    finally:
        fuseaux.utiliser_la_base_de_l_hote(None)


def test_base_de_l_hote_remplacee_pendant_que_l_api_tourne(base_de_l_hote):
    horloge = HorlogeSimulee(datetime(2026, 10, 23, tzinfo=UTC))
    programme = VerificationAuChangementDHeure(lambda: "Africa/Casablanca", horloge, lambda: None, pas_s=0.01)
    programme.demarrer()
    try:
        attendre(lambda: programme.prevue == datetime(2026, 10, 25, 1, tzinfo=UTC))
        assert fuseaux.posix_du_moment("Africa/Casablanca", ETE) == "CEST-2"

        # Mise à jour de l'OS : Casablanca passe aux règles de Tokyo (UTC+9, sans changement d'heure).
        poser(base_de_l_hote, "Africa/Casablanca", "Asia/Tokyo")
        (base_de_l_hote / "+VERSION").write_text("2099b\n")

        attendre(lambda: programme.prevue is None)
        assert fuseaux.base().version == "2099b"
        assert fuseaux.posix_du_moment("Africa/Casablanca", ETE) == "JST-9"
    finally:
        programme.arreter()
