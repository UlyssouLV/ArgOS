"""Espace du volume des enregistrements et Seuil de place disque (signal seul)."""

import pytest

from stack_compose import client_du_site
from test_cameras import connecte  # noqa: F401

SEUIL_DEFAUT = 1_073_741_824  # 1 Go
SEUIL_MIN = 104_857_600  # 100 Mo
CONSERVATION_DEFAUT = 1


@pytest.fixture(autouse=True)
def reglages_remis(administrateur):
    """Réglages Site globaux : chaque test repart des défauts et y revient."""

    def remettre() -> None:
        with client_du_site() as c:
            assert c.post(
                "/api/session",
                json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
            ).status_code == 204
            assert c.patch(
                "/api/reglages-site",
                json={"conservation_h": CONSERVATION_DEFAUT, "seuil_octets_libres": SEUIL_DEFAUT},
            ).status_code == 200

    remettre()
    yield
    remettre()


def test_seuil_par_defaut_un_go(connecte):
    reponse = connecte.get("/api/reglages-site")

    assert reponse.status_code == 200
    assert reponse.json()["seuil_octets_libres"] == SEUIL_DEFAUT


def test_regler_le_seuil_le_persiste(connecte):
    seuil = 512 * 1024 * 1024
    reponse = connecte.patch("/api/reglages-site", json={"seuil_octets_libres": seuil})

    assert reponse.status_code == 200
    assert reponse.json()["seuil_octets_libres"] == seuil
    assert connecte.get("/api/reglages-site").json()["seuil_octets_libres"] == seuil


def test_seuil_sous_le_plancher_refuse(connecte):
    avant = connecte.get("/api/reglages-site").json()["seuil_octets_libres"]
    reponse = connecte.patch("/api/reglages-site", json={"seuil_octets_libres": SEUIL_MIN - 1})

    assert reponse.status_code == 422
    assert connecte.get("/api/reglages-site").json()["seuil_octets_libres"] == avant


def test_espace_volume_total_libre_utilise(connecte):
    reponse = connecte.get("/api/espace-enregistrements")

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["total_o"] > 0
    assert corps["libre_o"] >= 0
    assert corps["utilise_o"] == corps["total_o"] - corps["libre_o"]
    assert "sous_seuil" in corps


def test_espace_sans_session_401(client):
    assert client.get("/api/espace-enregistrements").status_code == 401


def test_sous_seuil_quand_le_seuil_depasse_la_place_libre(connecte):
    libre = connecte.get("/api/espace-enregistrements").json()["libre_o"]
    assert connecte.patch("/api/reglages-site", json={"seuil_octets_libres": libre + 1}).status_code == 200

    assert connecte.get("/api/espace-enregistrements").json()["sous_seuil"] is True


def test_pas_sous_seuil_quand_assez_de_place(connecte):
    assert connecte.patch("/api/reglages-site", json={"seuil_octets_libres": SEUIL_MIN}).status_code == 200

    assert connecte.get("/api/espace-enregistrements").json()["sous_seuil"] is False
