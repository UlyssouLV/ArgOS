"""Connexion de l'Administrateur à l'API du Site, vue de l'extérieur de la stack."""

import httpx

from conftest import attendre_api, client_du_site, compose
from stack_compose import COOKIE_SESSION


def se_connecter(client: httpx.Client, identifiant: str, mot_de_passe: str) -> httpx.Response:
    return client.post(
        "/api/session",
        json={"identifiant": identifiant, "mot_de_passe": mot_de_passe},
    )


def attributs(set_cookie: str) -> set[str]:
    """Attributs d'un `Set-Cookie` (après le nom et la valeur), en minuscules."""
    return {attribut.strip().lower() for attribut in set_cookie.split(";")[1:]}


def test_bons_identifiants_ouvrent_une_session(client, administrateur):
    reponse = se_connecter(client, **administrateur)

    assert reponse.status_code == 204
    set_cookie = reponse.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE_SESSION}=")
    assert {"secure", "httponly", "samesite=lax"} <= attributs(set_cookie)

    moi = client.get("/api/moi")
    assert moi.status_code == 200
    assert moi.json() == {"identifiant": administrateur["identifiant"]}


def test_mauvais_mot_de_passe_ou_identifiant_meme_401(client, administrateur):
    mauvais_mot_de_passe = se_connecter(
        client, administrateur["identifiant"], administrateur["mot_de_passe"] + "x"
    )
    mauvais_identifiant = se_connecter(
        client, administrateur["identifiant"] + "x", administrateur["mot_de_passe"]
    )

    assert mauvais_mot_de_passe.status_code == 401
    assert mauvais_identifiant.status_code == 401
    assert mauvais_mot_de_passe.json() == mauvais_identifiant.json()
    assert COOKIE_SESSION not in client.cookies


def test_moi_sans_cookie_est_refuse(client):
    assert client.get("/api/moi").status_code == 401


def test_moi_avec_un_cookie_inconnu_est_refuse(client):
    client.cookies.set(COOKIE_SESSION, "inconnu")

    assert client.get("/api/moi").status_code == 401


def test_deconnexion_revoque_la_session_cote_serveur(client, administrateur):
    se_connecter(client, **administrateur)
    jeton = client.cookies[COOKIE_SESSION]

    deconnexion = client.delete("/api/session")
    assert deconnexion.status_code == 204
    # Supprimé avec les mêmes attributs qu'à la pose.
    assert {"secure", "httponly", "samesite=lax"} <= attributs(deconnexion.headers["set-cookie"])

    with client_du_site() as autre:
        autre.cookies.set(COOKIE_SESSION, jeton)
        assert autre.get("/api/moi").status_code == 401


def test_session_survit_au_redemarrage_de_l_api(client, administrateur):
    se_connecter(client, **administrateur)

    compose("restart", "api")
    attendre_api()

    assert client.get("/api/moi").status_code == 200


def test_documentation_openapi_servie(client):
    reponse = client.get("/api/docs")

    assert reponse.status_code == 200
    assert "swagger" in reponse.text.lower()
