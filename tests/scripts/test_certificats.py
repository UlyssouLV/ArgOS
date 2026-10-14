"""Service `certificats` (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md).

Lancé comme dans la stack, sur des dossiers temporaires à la place de ses deux volumes : `autorite` (Autorité
du Site, clé comprise) et `certificats-serveur` (ce que `web` lit).
"""

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

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


def certificat_de(pem: bytes) -> x509.Certificate:
    return x509.load_pem_x509_certificate(pem)


def certificat(chemin: Path) -> x509.Certificate:
    return certificat_de(chemin.read_bytes())


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


def empreinte(cert: x509.Certificate) -> bytes:
    return cert.fingerprint(hashes.SHA256())


def test_ip_declaree_changee_regenere_le_certificat_serveur_avec_la_meme_autorite(lancer):
    premier = lancer("192.168.1.20")
    autorite = empreinte(certificat(premier.autorite / "autorite.crt"))
    ancien = certificat(premier.serveur / "serveur.crt")

    second = lancer("192.168.1.30")

    serveur = certificat(second.serveur / "serveur.crt")
    assert noms(serveur) == {"localhost", "127.0.0.1", "192.168.1.30"}
    assert serveur.serial_number != ancien.serial_number
    assert empreinte(certificat(second.autorite / "autorite.crt")) == autorite
    serveur.verify_directly_issued_by(certificat(second.autorite / "autorite.crt"))


def test_certificat_serveur_valide_et_san_inchanges_est_garde(lancer):
    premier = lancer("192.168.1.20,argos.local,fe80::1")
    ancien = (premier.serveur / "serveur.crt").read_bytes()

    # Mêmes noms, autre ordre, un doublon et l'IPv6 écrite autrement : rien n'a changé pour le certificat.
    second = lancer("argos.local,fe80:0:0::1,192.168.1.20,192.168.1.20")

    assert (second.serveur / "serveur.crt").read_bytes() == ancien
    assert certificat(second.serveur / "serveur.crt").serial_number == certificat_de(ancien).serial_number


def autorite_et_serveur_deposes(autorite: Path, serveur: Path, *, reste: timedelta) -> x509.Certificate:
    """Autorité du Site et certificat serveur signé par elle, aux bons noms, à qui il reste `reste`."""
    cle_autorite = ec.generate_private_key(ec.SECP256R1())
    sujet = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Autorité du Site ArgOS")])
    maintenant = datetime.now(UTC)
    cert_autorite = (
        x509.CertificateBuilder()
        .subject_name(sujet)
        .issuer_name(sujet)
        .public_key(cle_autorite.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=1))
        .not_valid_after(maintenant + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(cle_autorite.public_key()), critical=False)
        .sign(cle_autorite, hashes.SHA256())
    )
    cle_serveur = ec.generate_private_key(ec.SECP256R1())
    cert_serveur = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "ArgOS")]))
        .issuer_name(sujet)
        .public_key(cle_serveur.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=397) + reste)
        .not_valid_after(maintenant + reste)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(cle_autorite, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    sans_chiffrement = serialization.NoEncryption()
    pkcs8 = serialization.PrivateFormat.PKCS8
    (autorite / "autorite.key").write_bytes(cle_autorite.private_bytes(pem, pkcs8, sans_chiffrement))
    (autorite / "autorite.crt").write_bytes(cert_autorite.public_bytes(pem))
    (serveur / "serveur.key").write_bytes(cle_serveur.private_bytes(pem, pkcs8, sans_chiffrement))
    (serveur / "serveur.crt").write_bytes(cert_serveur.public_bytes(pem))
    return cert_serveur


@pytest.fixture
def dossiers(lancer, tmp_path: Path) -> tuple[Path, Path]:
    """Les deux volumes de `lancer`, à remplir avant le lancement."""
    return tmp_path / "autorite", tmp_path / "certificats-serveur"


def test_certificat_serveur_qui_expire_dans_moins_de_30_jours_est_regenere(lancer, dossiers):
    autorite, serveur = dossiers
    ancien = autorite_et_serveur_deposes(autorite, serveur, reste=timedelta(days=29))
    cert_autorite = (autorite / "autorite.crt").read_bytes()

    lancement = lancer()

    nouveau = certificat(lancement.serveur / "serveur.crt")
    assert nouveau.serial_number != ancien.serial_number
    assert duree(nouveau) == timedelta(days=397)
    assert (lancement.autorite / "autorite.crt").read_bytes() == cert_autorite
    nouveau.verify_directly_issued_by(certificat_de(cert_autorite))


def test_certificat_serveur_a_qui_il_reste_plus_de_30_jours_est_garde(lancer, dossiers):
    autorite, serveur = dossiers
    ancien = autorite_et_serveur_deposes(autorite, serveur, reste=timedelta(days=31))

    lancement = lancer()

    assert certificat(lancement.serveur / "serveur.crt").serial_number == ancien.serial_number
