"""Plages d'octets de la relecture (#143) : Safari ouvre une `<video>` par `Range: bytes=0-1` et veut un `206`.

Tests unitaires de `relecture.plage` ; le test de bout en bout est dans test_relecture.py.
"""

import pytest

from argos_api import relecture

TAILLE = 100


@pytest.mark.parametrize(
    ("entete", "attendue"),
    [
        ("bytes=0-1", (0, 2)),
        ("bytes=10-19", (10, 20)),
        ("bytes=90-", (90, 100)),
        ("bytes=90-500", (90, 100)),
        ("bytes=-10", (90, 100)),
        ("bytes=-500", (0, 100)),
        (" bytes = 5 - 6 ", (5, 7)),
    ],
)
def test_une_plage_satisfaisable_donne_ses_bornes(entete, attendue):
    assert relecture.plage(entete, TAILLE) == attendue


@pytest.mark.parametrize("entete", [None, "", "octets=0-1", "bytes=0-1,5-6", "bytes=a-b", "bytes=5-2", "bytes=-"])
def test_sans_plage_lisible_le_fichier_entier_est_servi(entete):
    assert relecture.plage(entete, TAILLE) is None


@pytest.mark.parametrize("entete", ["bytes=100-", "bytes=150-200", "bytes=-0"])
def test_une_plage_hors_du_fichier_est_insatisfaisable(entete):
    with pytest.raises(relecture.PlageInsatisfaisable):
        relecture.plage(entete, TAILLE)


def test_un_fichier_vide_n_a_aucune_plage_satisfaisable():
    with pytest.raises(relecture.PlageInsatisfaisable):
        relecture.plage("bytes=0-1", 0)
