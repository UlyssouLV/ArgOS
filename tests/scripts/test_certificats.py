"""Service `certificats` (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md).

Lancé comme dans la stack, sur des dossiers temporaires à la place de ses deux volumes : `autorite` (Autorité
du Site, clé comprise) et `certificats-serveur` (ce que `web` lit).
"""

import subprocess
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import ip_address
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE = "argos-certificats-test"
DELAI_S = 60


@dataclass
class Lancement:
    sortie: str
    autorite: Path
    serveur: Path


@pytest.fixture(scope="session")
def image() -> str:
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(REPO_ROOT / "certificats")], check=True, capture_output=True)
    return IMAGE


@pytest.fixture
def lancer(image, tmp_path: Path):
    autorite = tmp_path / "autorite"
    serveur = tmp_path / "certificats-serveur"
    autorite.mkdir()
    serveur.mkdir()

    def _lancer(hotes: str = "") -> Lancement:
        proc = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{autorite}:/autorite",
                "-v", f"{serveur}:/certificats-serveur",
                "-e", f"MTX_WEBRTCADDITIONALHOSTS={hotes}",
                image,
            ],
            capture_output=True,
            text=True,
            timeout=DELAI_S,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return Lancement(proc.stdout + proc.stderr, autorite, serveur)

    return _lancer


def certificat(chemin: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(chemin.read_bytes())


def noms(cert: x509.Certificate) -> set[str]:
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return set(san.get_values_for_type(x509.DNSName)) | {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}


def duree(cert: x509.Certificate) -> timedelta:
    return cert.not_valid_after_utc - cert.not_valid_before_utc


def test_premier_lancement_cree_l_autorite_et_un_certificat_serveur_signe_par_elle(lancer):
    lancement = lancer("192.168.1.20,10.0.0.5")

    autorite = certificat(lancement.autorite / "autorite.crt")
    serveur = certificat(lancement.serveur / "serveur.crt")
    assert autorite.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert duree(autorite) >= timedelta(days=3650)
    serveur.verify_directly_issued_by(autorite)
    assert duree(serveur) == timedelta(days=397)
    assert noms(serveur) == {"localhost", "127.0.0.1", "192.168.1.20", "10.0.0.5"}
    assert x509.ExtendedKeyUsageOID.SERVER_AUTH in serveur.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value


def test_web_ne_recoit_que_la_partie_publique_de_l_autorite(lancer):
    lancement = lancer()

    assert sorted(p.name for p in lancement.serveur.iterdir()) == ["argos-ca.crt", "serveur.crt", "serveur.key"]
    assert (lancement.serveur / "argos-ca.crt").read_bytes() == (lancement.autorite / "autorite.crt").read_bytes()
    assert b"PRIVATE KEY" not in (lancement.serveur / "argos-ca.crt").read_bytes()


def test_sans_ip_declaree_le_certificat_serveur_ne_couvre_que_cette_machine(lancer):
    lancement = lancer()

    assert noms(certificat(lancement.serveur / "serveur.crt")) == {"localhost", "127.0.0.1"}


def test_un_nom_declare_est_couvert_comme_nom(lancer):
    lancement = lancer("argos.local")

    san = certificat(lancement.serveur / "serveur.crt").extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert "argos.local" in san.value.get_values_for_type(x509.DNSName)
    assert all(ip_address(ip) for ip in san.value.get_values_for_type(x509.IPAddress))


def test_l_empreinte_sha256_de_l_autorite_s_affiche(lancer):
    lancement = lancer()

    empreinte = certificat(lancement.autorite / "autorite.crt").fingerprint(hashes.SHA256()).hex(":").upper()
    assert empreinte in lancement.sortie


def test_second_lancement_garde_l_autorite(lancer):
    premier = lancer()
    autorite = (premier.autorite / "autorite.crt").read_bytes()
    cle = (premier.autorite / "autorite.key").read_bytes()

    second = lancer()

    assert (second.autorite / "autorite.crt").read_bytes() == autorite
    assert (second.autorite / "autorite.key").read_bytes() == cle
    certificat(second.serveur / "serveur.crt").verify_directly_issued_by(certificat(second.autorite / "autorite.crt"))
