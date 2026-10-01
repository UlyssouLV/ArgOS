"""Règles de session qui dépendent du temps ou de la configuration, l'application montée en processus."""

import pytest

from argos_api.app import creer_app
from argos_api.configuration import ConfigurationIncomplete
from conftest import MOT_DE_PASSE, se_connecter

MAUVAIS_MOT_DE_PASSE = MOT_DE_PASSE + "x"


def echouer(client, fois: int) -> None:
    for _ in range(fois):
        assert se_connecter(client, MAUVAIS_MOT_DE_PASSE).status_code == 401


# Expiration


def test_session_valide_a_23_h_59_refusee_a_24_h_malgre_l_activite(client, horloge):
    assert se_connecter(client).status_code == 204

    for _ in range(23):
        horloge.avancer(hours=1)
        assert client.get("/api/moi").status_code == 200
    horloge.avancer(minutes=59)
    assert client.get("/api/moi").status_code == 200

    horloge.avancer(minutes=1)
    assert client.get("/api/moi").status_code == 401


# Changement de mot de passe


def test_changer_le_mot_de_passe_refuse_les_sessions_ouvertes_avant(demarrer):
    avant = demarrer()
    assert se_connecter(avant).status_code == 204
    jeton = avant.cookies["argos_session"]

    apres = demarrer(mot_de_passe="un tout nouveau mot de passe")
    apres.cookies.set("argos_session", jeton)
    assert apres.get("/api/moi").status_code == 401

    apres.cookies.clear()
    assert se_connecter(apres, "un tout nouveau mot de passe").status_code == 204
    assert apres.get("/api/moi").status_code == 200


def test_redemarrer_sans_changer_le_mot_de_passe_garde_les_sessions(demarrer):
    avant = demarrer()
    assert se_connecter(avant).status_code == 204

    apres = demarrer()
    apres.cookies.set("argos_session", avant.cookies["argos_session"])
    assert apres.get("/api/moi").status_code == 200


# Frein à la force brute


def test_cinq_echecs_bloquent_la_connexion_meme_avec_le_bon_mot_de_passe(client):
    echouer(client, 5)

    reponse = se_connecter(client)

    assert reponse.status_code == 429
    assert "argos_session" not in client.cookies


def test_connexion_de_nouveau_possible_15_min_apres_le_blocage(client, horloge):
    echouer(client, 5)

    horloge.avancer(minutes=14, seconds=59)
    assert se_connecter(client).status_code == 429

    horloge.avancer(seconds=1)
    assert se_connecter(client).status_code == 204


def test_echecs_espaces_de_plus_de_15_min_ne_bloquent_pas(client, horloge):
    echouer(client, 4)
    horloge.avancer(minutes=15)
    echouer(client, 4)

    assert se_connecter(client).status_code == 204


def test_le_frein_repart_de_zero_au_redemarrage(demarrer):
    echouer(demarrer(), 5)

    assert se_connecter(demarrer()).status_code == 204


# Refus de démarrer


@pytest.mark.parametrize("variable", ["ARGOS_IDENTIFIANT", "ARGOS_MOT_DE_PASSE"])
@pytest.mark.parametrize("valeur", [None, ""], ids=["absente", "vide"])
def test_refuse_de_demarrer_sans_identifiant_ou_mot_de_passe(monkeypatch, url_base, variable, valeur):
    monkeypatch.setenv("ARGOS_IDENTIFIANT", "administrateur")
    monkeypatch.setenv("ARGOS_MOT_DE_PASSE", MOT_DE_PASSE)
    monkeypatch.setenv("ARGOS_URL_BASE", url_base)
    if valeur is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, valeur)

    with pytest.raises(ConfigurationIncomplete, match=variable):
        creer_app()
