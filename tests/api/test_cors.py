"""CORS de l'API du Site : seules les origines de `ARGOS_ORIGINES_AUTORISEES` appellent avec le cookie."""

import pytest

ORIGINE_AUTORISEE = "http://localhost:8080"  # défaut de ARGOS_ORIGINES_AUTORISEES (UI servie par web)
AUTRE_ORIGINE = "http://site-tiers.example"


@pytest.mark.parametrize("origine", [ORIGINE_AUTORISEE, "http://localhost:5173"])
def test_origine_autorisee_recoit_les_en_tetes_cors_avec_credentials(client, origine):
    reponse = client.get("/api/moi", headers={"Origin": origine})

    assert reponse.headers.get("access-control-allow-origin") == origine
    assert reponse.headers.get("access-control-allow-credentials") == "true"


def test_preflight_d_une_origine_autorisee_accepte_la_connexion(client):
    reponse = client.options(
        "/api/session",
        headers={
            "Origin": ORIGINE_AUTORISEE,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert reponse.status_code == 200
    assert reponse.headers.get("access-control-allow-origin") == ORIGINE_AUTORISEE
    assert reponse.headers.get("access-control-allow-credentials") == "true"


def test_autre_origine_n_est_pas_autorisee(client):
    simple = client.get("/api/moi", headers={"Origin": AUTRE_ORIGINE})
    preflight = client.options(
        "/api/session",
        headers={"Origin": AUTRE_ORIGINE, "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in simple.headers
    assert "access-control-allow-origin" not in preflight.headers
