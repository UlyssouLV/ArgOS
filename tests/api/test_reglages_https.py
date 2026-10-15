"""Réglages en ONVIF chiffré (docs/adr/0007-onvif-en-https-par-cle-memorisee.md), sur les Caméras simulées.

La 2 répond en HTTPS sur `443` (certificat auto-signé gardé dans un volume) et garde HTTP sur `8899` : ArgOS doit
choisir HTTPS, mémoriser l'empreinte de la clé publique du Certificat de l'Appareil au premier contact, puis la
vérifier. Ce que la caméra a reçu, et par où, se lit dans le journal de son simulateur.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from stack_compose import (
    IPS_SIMULEES,
    adresses_ip,
    camera_simulee_2_en_tls_ancien,
    compose,
    remettre_onvif_en_usine,
    requetes_onvif_recues,
)
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_onvif_simule import certificat_presente
from test_reglages import camera_simulee, lire  # noqa: F401 (fixtures)

SIMULATEUR_2 = "camera-simulee-2-onvif"


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


@pytest.fixture(scope="module")
def ip_api() -> str:
    """IP de l'API sur le réseau des Caméras simulées : celle que voient leurs simulateurs ONVIF."""
    (ip,) = [ip for ip in adresses_ip("api") if ip.startswith("172.30.")]
    return ip


def empreinte_spki(ip: str, port: int) -> str:
    """SHA-256 (hexadécimal) de la clé publique (SPKI) du certificat présenté en HTTPS à (IP, port)."""
    certificat = x509.load_der_x509_certificate(bytes.fromhex(certificat_presente(ip, port)))
    return hashlib.sha256(certificat.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def camera_lue(client, id_camera: int) -> dict:
    return client.get(f"/api/cameras/{id_camera}").json()


def sql(requete: str) -> None:
    compose("exec", "-T", "db", "psql", "-U", "argos", "-d", "argos", "-c", requete)


def test_simulee_2_lue_en_https_rien_d_autre_que_sur_443(connecte, camera_simulee, ip_api):
    depuis = datetime.now(UTC) - timedelta(seconds=1)
    id_camera = camera_simulee(2)

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    camera = camera_lue(connecte, id_camera)
    assert (camera["schema_onvif"], camera["port_onvif"]) == ("https", 443)
    # Le service média, annoncé en `http://…` sans port, est joint en HTTPS sur le port du contact.
    assert requetes_onvif_recues(SIMULATEUR_2, depuis, ip_api, "https:443")
    assert requetes_onvif_recues(SIMULATEUR_2, depuis, ip_api, "http:8899") == []


def test_modification_en_https(connecte, camera_simulee, ip_api):
    id_camera = camera_simulee(2)
    assert lire(connecte, id_camera).status_code == 200
    depuis = datetime.now(UTC) - timedelta(seconds=1)

    reponse = connecte.patch(
        f"/api/cameras/{id_camera}/reglages", json={"incrustations": {"nom": {"texte": "HTTPS"}}}, timeout=30
    )

    assert reponse.status_code == 200
    assert reponse.json()["champs"][0]["statut"] == "pris"
    assert requetes_onvif_recues(SIMULATEUR_2, depuis, ip_api, "http:8899") == []
    remettre_onvif_en_usine()


def test_empreinte_memorisee_au_premier_contact_puis_reutilisee(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    avant = datetime.now(UTC)

    premiere = lire(connecte, id_camera).json()["securite"]
    seconde = lire(connecte, id_camera).json()["securite"]

    attendue = empreinte_spki(IPS_SIMULEES[2], 443)
    assert {cle: premiere[cle] for cle in ("chiffre", "empreinte", "tls_ancien")} == {
        "chiffre": True,
        "empreinte": attendue,
        "tls_ancien": False,
    }
    memorisee_le = datetime.fromisoformat(premiere["empreinte_memorisee_le"])
    assert avant - timedelta(seconds=5) <= memorisee_le <= datetime.now(UTC) + timedelta(seconds=5)
    assert seconde == premiere


def test_camera_retenue_en_http_passe_en_https(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    # Comme une Caméra réglée en 0.6.0 : HTTP sur 8899, aucune clé.
    sql(f"UPDATE cameras SET schema_onvif = 'http', port_onvif = 8899 WHERE id = {id_camera}")

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert reponse.json()["securite"]["chiffre"] is True
    camera = camera_lue(connecte, id_camera)
    assert (camera["schema_onvif"], camera["port_onvif"]) == ("https", 443)


def test_cle_differente_refusee(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    assert lire(connecte, id_camera).status_code == 200
    sql(f"UPDATE cameras SET empreinte_onvif = '{'0' * 64}' WHERE id = {id_camera}")

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 502
    assert reponse.json()["code"] == "certificat_change"


def test_camera_en_http_seulement_non_chiffree(connecte, camera_simulee):
    id_camera = camera_simulee(4)

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert reponse.json()["securite"] == {
        "chiffre": False,
        "empreinte": None,
        "empreinte_memorisee_le": None,
        "tls_ancien": False,
    }
    camera = camera_lue(connecte, id_camera)
    assert (camera["schema_onvif"], camera["port_onvif"]) == ("http", 80)


@pytest.fixture
def tls_ancien():
    camera_simulee_2_en_tls_ancien()
    yield
    remettre_onvif_en_usine()


def test_tls_1_0_accepte_et_signale(connecte, camera_simulee, tls_ancien):
    reponse = lire(connecte, camera_simulee(2))

    assert reponse.status_code == 200
    securite = reponse.json()["securite"]
    assert securite["chiffre"] is True
    assert securite["tls_ancien"] is True
