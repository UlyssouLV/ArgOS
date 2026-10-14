"""Service `certificats` (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md).

Lancé comme dans la stack, sur des dossiers temporaires à la place de ses deux volumes : `autorite` (Autorité
du Site, clé comprise) et `certificats-serveur` (ce que `web` lit), et du dossier d'un certificat fourni par
l'Administrateur (`ARGOS_CERTIFICAT_DOSSIER`).
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
    code: int
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
    # Ouverts à l'utilisateur 101 du service, comme ses volumes neufs (Dockerfile).
    autorite.mkdir()
    serveur.mkdir()
    autorite.chmod(0o777)
    serveur.chmod(0o777)

    def _lancer(hotes: str = "", fourni: Path | None = None, *, echec: bool = False) -> Lancement:
        """`fourni` : dossier du certificat de l'Administrateur, monté comme le fait compose.yaml."""
        options_fourni = (
            ["-v", f"{fourni}:/certificat-fourni:ro", "-e", f"ARGOS_CERTIFICAT_DOSSIER={fourni}"] if fourni else []
        )
        proc = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{autorite}:/autorite",
                "-v", f"{serveur}:/certificats-serveur",
                "-e", f"MTX_WEBRTCADDITIONALHOSTS={hotes}",
                *options_fourni,
                image,
            ],
            capture_output=True,
            text=True,
            timeout=DELAI_S,
        )
        lancement = Lancement(proc.returncode, proc.stdout + proc.stderr, autorite, serveur)
        assert (proc.returncode != 0) == echec, lancement.sortie
        return lancement

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

    assert sorted(p.name for p in lancement.serveur.iterdir()) == ["argos-ca.crt", "public", "serveur.crt", "serveur.key"]
    assert (lancement.serveur / "argos-ca.crt").read_bytes() == (lancement.autorite / "autorite.crt").read_bytes()
    assert b"PRIVATE KEY" not in (lancement.serveur / "argos-ca.crt").read_bytes()


def test_api_ne_recoit_que_le_certificat_presente_par_le_site(lancer):
    lancement = lancer()

    public = lancement.serveur / "public"
    assert [p.name for p in public.iterdir()] == ["serveur.crt"]
    assert (public / "serveur.crt").read_bytes() == (lancement.serveur / "serveur.crt").read_bytes()


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


def autorite_de_test() -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """CA de test, étrangère à ArgOS : celle d'un nom de domaine ou d'un VPN de l'Administrateur."""
    cle = ec.generate_private_key(ec.SECP256R1())
    sujet = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "CA de test de l'Administrateur")])
    maintenant = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(sujet)
        .issuer_name(sujet)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=1))
        .not_valid_after(maintenant + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(cle, hashes.SHA256())
    )
    return cle, cert


def certificat_fourni(dossier: Path) -> tuple[bytes, bytes]:
    """`certificat.crt` et `cle.key` de l'Administrateur, signés par une CA de test ; renvoie leurs octets."""
    cle_ca, ca = autorite_de_test()
    cle = ec.generate_private_key(ec.SECP256R1())
    maintenant = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "argos.example.org")]))
        .issuer_name(ca.subject)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=1))
        # Expire bientôt : un certificat fourni n'est jamais renouvelé par ArgOS.
        .not_valid_after(maintenant + timedelta(days=10))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("argos.example.org")]), critical=False)
        .sign(cle_ca, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    # Chaîne complète, comme la livre une CA : le certificat puis la CA.
    octets_cert = cert.public_bytes(pem) + ca.public_bytes(pem)
    octets_cle = cle.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    dossier.mkdir(exist_ok=True)
    (dossier / "certificat.crt").write_bytes(octets_cert)
    (dossier / "cle.key").write_bytes(octets_cle)
    return octets_cert, octets_cle


def test_certificat_fourni_est_copie_tel_quel_pour_web(lancer, tmp_path: Path):
    octets_cert, octets_cle = certificat_fourni(tmp_path / "fourni")

    lancement = lancer("192.168.1.20", tmp_path / "fourni")

    assert (lancement.serveur / "serveur.crt").read_bytes() == octets_cert
    assert (lancement.serveur / "serveur.key").read_bytes() == octets_cle
    assert (lancement.serveur / "public" / "serveur.crt").read_bytes() == octets_cert


def test_certificat_fourni_sans_autorite_du_site(lancer, tmp_path: Path):
    certificat_fourni(tmp_path / "fourni")

    lancement = lancer(fourni=tmp_path / "fourni")

    assert list(lancement.autorite.iterdir()) == []
    assert not (lancement.serveur / "argos-ca.crt").exists()
    assert "Empreinte SHA-256 de l'Autorité" not in lancement.sortie


def test_certificat_fourni_remplace_l_autorite_d_un_lancement_precedent(lancer, tmp_path: Path):
    premier = lancer()
    autorite = (premier.autorite / "autorite.crt").read_bytes()
    octets_cert, _ = certificat_fourni(tmp_path / "fourni")

    second = lancer(fourni=tmp_path / "fourni")

    assert (second.serveur / "serveur.crt").read_bytes() == octets_cert
    assert not (second.serveur / "argos-ca.crt").exists()
    # L'Autorité reste dans son volume : sans la variable, le Site la sert de nouveau, rien à réinstaller.
    assert (second.autorite / "autorite.crt").read_bytes() == autorite


def test_sans_la_variable_l_autorite_du_site_revient_apres_un_certificat_fourni(lancer, tmp_path: Path):
    certificat_fourni(tmp_path / "fourni")
    lancer(fourni=tmp_path / "fourni")

    lancement = lancer()

    autorite = certificat(lancement.autorite / "autorite.crt")
    certificat(lancement.serveur / "serveur.crt").verify_directly_issued_by(autorite)
    assert (lancement.serveur / "argos-ca.crt").read_bytes() == (lancement.autorite / "autorite.crt").read_bytes()


@pytest.mark.parametrize("manquant", ["certificat.crt", "cle.key"])
def test_certificat_fourni_incomplet_fait_echouer_avec_un_message_clair(lancer, tmp_path: Path, manquant):
    certificat_fourni(tmp_path / "fourni")
    (tmp_path / "fourni" / manquant).unlink()

    lancement = lancer(fourni=tmp_path / "fourni", echec=True)

    assert manquant in lancement.sortie
    assert "ARGOS_CERTIFICAT_DOSSIER" in lancement.sortie
    assert str(tmp_path / "fourni") in lancement.sortie
    assert list(lancement.serveur.iterdir()) == []
