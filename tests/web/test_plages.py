"""Plages enregistrées, fenêtre glissante et Plage suivante de la Relecture continue (ADR 0018, #165).

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

    assert _appeler("fenetre", plage, _ms("10:12:34")) == {"start": "2026-10-26T10:12:34.000Z", "duration": 180}


def test_la_fenetre_est_coupee_a_la_fin_de_la_plage():
    plage = _intervalle("10:00:00", "10:05:00")

    assert _appeler("fenetre", plage, _ms("10:04:00")) == {"start": "2026-10-26T10:04:00.000Z", "duration": 60}


@pytest.mark.parametrize("heure", ["09:59:59", "10:05:00", "10:30:00"])
def test_pas_de_fenetre_hors_de_la_plage_ou_a_sa_fin(heure):
    assert _appeler("fenetre", _intervalle("10:00:00", "10:05:00"), _ms(heure)) is None


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
