"""Plages enregistrées, fenêtre de lecture et Plage suivante de la Relecture continue (ADR 0018, #165).

Tests unitaires de `web/src/plages.ts`, exécuté tel quel par Node (types effacés) ; le lecteur est testé dans
test_relecture.py.
"""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

PLAGES = Path(__file__).resolve().parents[2] / "web" / "src" / "plages.ts"
NODE = shutil.which("node") or "node"


def _appeler(fonction: str, *arguments) -> object:
    """Résultat JSON de `fonction(...arguments)` exportée par plages.ts."""
    script = (
        f"const m = await import({json.dumps(PLAGES.as_uri())});"
        f"console.log(JSON.stringify(m.{fonction}(...{json.dumps(list(arguments))}) ?? null));"
    )
    sortie = subprocess.run(
        [NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(sortie.stdout)


def _iso(heure: str) -> str:
    """Heure `HH:MM:SS` du 26/10/2026 UTC, en RFC 3339."""
    return f"2026-10-26T{heure}Z"


def _ms(heure: str) -> int:
    return int(datetime.fromisoformat(_iso(heure)).timestamp() * 1000)


def _intervalle(debut: str, fin: str) -> dict:
    return {"debut": _iso(debut), "fin": _iso(fin)}


def test_des_segments_contigus_forment_une_seule_plage():
    segments = [_intervalle("10:00:00", "10:01:00"), _intervalle("10:01:00", "10:02:00"), _intervalle("10:02:00", "10:03:00")]

    assert _appeler("plagesEnregistrees", segments) == [_intervalle("10:00:00", "10:03:00")]


def test_un_ecart_d_ecriture_sous_la_tolerance_reste_contigu():
    # Fin = dernière écriture du fichier : elle peut précéder de peu le début du Segment suivant.
    segments = [_intervalle("10:00:00", "10:00:59.500"), _intervalle("10:01:00", "10:02:00")]

    assert _appeler("plagesEnregistrees", segments) == [_intervalle("10:00:00", "10:02:00")]


def test_un_trou_separe_deux_plages():
    segments = [
        _intervalle("10:00:00", "10:01:00"),
        _intervalle("10:01:00", "10:02:00"),
        _intervalle("10:05:00", "10:06:00"),
        _intervalle("10:06:00", "10:07:00"),
    ]

    assert _appeler("plagesEnregistrees", segments) == [_intervalle("10:00:00", "10:02:00"), _intervalle("10:05:00", "10:07:00")]


def test_les_segments_sont_regroupes_dans_l_ordre_du_temps():
    segments = [_intervalle("10:05:00", "10:06:00"), _intervalle("10:01:00", "10:02:00"), _intervalle("10:00:00", "10:01:00")]

    assert _appeler("plagesEnregistrees", segments) == [_intervalle("10:00:00", "10:02:00"), _intervalle("10:05:00", "10:06:00")]


def test_sans_segment_aucune_plage():
    assert _appeler("plagesEnregistrees", []) == []


def test_la_fenetre_dure_environ_trois_minutes_depuis_l_instant():
    plage = _intervalle("10:00:00", "11:00:00")

    assert _appeler("fenetreDans", plage, _ms("10:12:34")) == {"start": "2026-10-26T10:12:34.000Z", "duration": 180}


def test_la_fenetre_est_coupee_a_la_fin_de_la_plage():
    plage = _intervalle("10:00:00", "10:05:00")

    assert _appeler("fenetreDans", plage, _ms("10:04:00")) == {"start": "2026-10-26T10:04:00.000Z", "duration": 60}


@pytest.mark.parametrize("heure", ["09:59:59", "10:04:59.500", "10:05:00", "10:30:00"])
def test_pas_de_fenetre_hors_de_la_plage_ou_a_moins_d_une_seconde_de_sa_fin(heure):
    # Un reste de moins d'une seconde ne se lit pas : la fenêtre n'englobe jamais le trou qui suit pour l'allonger.
    assert _appeler("fenetreDans", _intervalle("10:00:00", "10:05:00"), _ms(heure)) is None


PLAGES_DU_JOUR = [_intervalle("10:00:00", "10:05:00"), _intervalle("10:20:00", "10:25:00")]


def test_la_plage_courante_couvre_l_instant():
    assert _appeler("plageCourante", PLAGES_DU_JOUR, _ms("10:22:00")) == _intervalle("10:20:00", "10:25:00")


def test_un_trou_n_a_pas_de_plage_courante():
    assert _appeler("plageCourante", PLAGES_DU_JOUR, _ms("10:10:00")) is None


@pytest.mark.parametrize("heure", ["10:05:00", "10:10:00"])
def test_apres_la_fin_d_une_plage_ou_dans_un_trou_vient_le_debut_de_la_suivante(heure):
    assert _appeler("plageSuivante", PLAGES_DU_JOUR, _ms(heure)) == _intervalle("10:20:00", "10:25:00")


def test_apres_la_derniere_plage_du_jour_plus_de_plage():
    assert _appeler("plageSuivante", PLAGES_DU_JOUR, _ms("10:25:00")) is None


def test_la_fenetre_d_un_instant_fractionnaire_finit_a_la_fin_de_la_plage():
    # Un clic tombe entre deux millisecondes : `start` et `duration` restent cohérents, la fenêtre s'arrête net.
    plage = _intervalle("10:00:00", "10:05:00")

    assert _appeler("fenetreDans", plage, _ms("10:04:00") + 0.7) == {"start": "2026-10-26T10:04:00.000Z", "duration": 60}


FENETRE = {"start": _iso("10:00:00"), "duration": 180}


@pytest.mark.parametrize(("position", "vitesse"), [(150, 1), (170, 2), (0, 16)])
def test_la_fenetre_se_renouvelle_a_l_approche_de_sa_fin_en_temps_reel(position, vitesse):
    # 30 s de lecture au plus : la suite a le temps de se charger, à ×16 dès le début d'une fenêtre de 3 min.
    assert _appeler("aRenouveler", FENETRE, position, vitesse) is True


@pytest.mark.parametrize(("position", "vitesse"), [(0, 1), (100, 1), (0, 4)])
def test_la_fenetre_ne_se_renouvelle_pas_loin_de_sa_fin(position, vitesse):
    assert _appeler("aRenouveler", FENETRE, position, vitesse) is False


SEGMENTS_DU_JOUR = [
    _intervalle("10:00:00", "10:01:00"),
    _intervalle("10:01:00", "10:02:00"),
    _intervalle("10:20:00", "10:21:00"),
]


def test_la_fenetre_depuis_un_instant_d_une_plage_part_de_cet_instant():
    assert _appeler("fenetreDepuis", SEGMENTS_DU_JOUR, _ms("10:00:30")) == {"start": _iso("10:00:30.000"), "duration": 90}


@pytest.mark.parametrize("heure", ["10:02:00", "10:10:00", "10:19:59"])
def test_la_fenetre_depuis_un_trou_ou_la_fin_d_une_plage_part_du_debut_de_la_suivante(heure):
    assert _appeler("fenetreDepuis", SEGMENTS_DU_JOUR, _ms(heure)) == {"start": _iso("10:20:00.000"), "duration": 60}


def test_apres_la_derniere_plage_plus_de_fenetre():
    assert _appeler("fenetreDepuis", SEGMENTS_DU_JOUR, _ms("10:21:00")) is None


def test_la_fenetre_dans_la_plage_ne_saute_pas_de_trou():
    # Fin d'une Plage, la suivante plus loin : rien tant qu'un Segment fermé ne la prolonge pas.
    assert _appeler("fenetreDansLaPlage", SEGMENTS_DU_JOUR, _ms("10:02:00")) is None
    prolongee = [*SEGMENTS_DU_JOUR, _intervalle("10:02:00", "10:03:00")]
    assert _appeler("fenetreDansLaPlage", prolongee, _ms("10:02:00")) == {"start": _iso("10:02:00.000"), "duration": 60}


def test_la_fin_d_une_fenetre_retombe_sur_la_milliseconde():
    assert _appeler("finDeFenetre", {"start": _iso("10:00:00.000"), "duration": 59.9996}) == _ms("10:01:00")


def test_deux_fenetres_identiques_demandent_la_meme_video():
    assert _appeler("memeFenetre", FENETRE, dict(FENETRE)) is True
    assert _appeler("memeFenetre", FENETRE, FENETRE | {"duration": 120}) is False
    assert _appeler("memeFenetre", FENETRE, None) is False


def test_la_duree_d_une_plage_en_secondes():
    assert _appeler("dureeS", _intervalle("10:00:00", "10:02:30")) == 150
