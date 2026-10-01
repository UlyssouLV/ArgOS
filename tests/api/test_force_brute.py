"""Frein à la force brute vu de l'extérieur de la stack.

Le compteur vit en mémoire de l'API : le test redémarre `api` avant (compteur à zéro malgré les
échecs des autres tests) et après (pour ne pas laisser la connexion bloquée 15 min).
"""

import pytest

from conftest import attendre_api, compose
from test_connexion import COOKIE_SESSION, se_connecter


def redemarrer_api() -> None:
    compose("restart", "api")
    attendre_api()


@pytest.fixture
def compteur_a_zero():
    redemarrer_api()
    yield
    redemarrer_api()


def test_cinq_echecs_puis_429_meme_avec_le_bon_mot_de_passe(compteur_a_zero, client, administrateur):
    mauvais = {**administrateur, "mot_de_passe": administrateur["mot_de_passe"] + "x"}
    for _ in range(5):
        assert se_connecter(client, **mauvais).status_code == 401

    reponse = se_connecter(client, **administrateur)

    assert reponse.status_code == 429
    assert COOKIE_SESSION not in client.cookies
