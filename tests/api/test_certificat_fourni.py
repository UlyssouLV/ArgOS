"""Certificat fourni par l'Administrateur (`ARGOS_CERTIFICAT_DOSSIER`), servi à la place de l'Autorité du Site.

`certificats` et `web` sont recréés avec la variable, puis sans : le Site revient à l'Autorité du Site, que
les autres tests utilisent.
"""

import shutil
import socket
import ssl
import subprocess
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from stack_compose import REPO_ROOT, URL_SITE, attendre_api, compose, recreer_le_site

PORTS_HTTP = (80, 8080)
# Hors de tmp_path pytest (0700) : le service `certificats` (uid 101) doit pouvoir traverser le dossier monté.
DOSSIER_CERTIFICAT_FOURNI = REPO_ROOT / ".tmp-certificat-fourni"


def certificat_signe_par_une_ca_de_test(dossier: Path) -> tuple[str, bytes]:
    """`certificat.crt` (chaîne comprise) et `cle.key` dans `dossier` ; renvoie la CA (PEM) et le certificat (DER)."""
    maintenant = datetime.now(UTC)
    cle_ca = ec.generate_private_key(ec.SECP256R1())
    sujet_ca = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "CA de test de l'Administrateur")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(sujet_ca)
        .issuer_name(sujet_ca)
        .public_key(cle_ca.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=1))
        .not_valid_after(maintenant + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(cle_ca.public_key()), critical=False)
        .sign(cle_ca, hashes.SHA256())
    )
    cle = ec.generate_private_key(ec.SECP256R1())
    certificat = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "argos.example.org")]))
        .issuer_name(sujet_ca)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=1))
        .not_valid_after(maintenant + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("argos.example.org"), x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cle_ca.public_key()), critical=False)
        .sign(cle_ca, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    dossier.mkdir(parents=True, exist_ok=True)
    dossier.chmod(0o755)
    chemin_crt = dossier / "certificat.crt"
    chemin_cle = dossier / "cle.key"
    chemin_crt.write_bytes(certificat.public_bytes(pem) + ca.public_bytes(pem))
    chemin_cle.write_bytes(
        cle.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    # Lisibles par l'utilisateur 101 du service `certificats` (dossiers pytest en 0700 sinon).
    chemin_crt.chmod(0o644)
    chemin_cle.chmod(0o644)
    return ca.public_bytes(pem).decode(), certificat.public_bytes(serialization.Encoding.DER)


@pytest.fixture(scope="module")
def certificat_fourni():
    """Le Site sert un certificat fourni pendant le module : la CA de test (PEM) et ce certificat (DER)."""
    shutil.rmtree(DOSSIER_CERTIFICAT_FOURNI, ignore_errors=True)
    ca, certificat = certificat_signe_par_une_ca_de_test(DOSSIER_CERTIFICAT_FOURNI)
    recreer_le_site(DOSSIER_CERTIFICAT_FOURNI)
    yield ca, certificat
    recreer_le_site()
    attendre_api()
    shutil.rmtree(DOSSIER_CERTIFICAT_FOURNI, ignore_errors=True)


def test_https_localhost_presente_exactement_le_certificat_fourni(certificat_fourni):
    ca, certificat = certificat_fourni

    # Validé contre la CA de test de l'Administrateur, pas contre l'Autorité du Site.
    with socket.create_connection(("localhost", 443), timeout=5) as brut:
        with ssl.create_default_context(cadata=ca).wrap_socket(brut, server_hostname="localhost") as tls:
            assert tls.getpeercert(binary_form=True) == certificat


@pytest.mark.parametrize("url", [*(f"http://localhost:{port}" for port in PORTS_HTTP), URL_SITE])
def test_sans_autorite_du_site_argos_ca_crt_repond_404(certificat_fourni, url):
    ca, _ = certificat_fourni

    reponse = httpx.get(f"{url}/argos-ca.crt", verify=ssl.create_default_context(cadata=ca), follow_redirects=False)

    assert reponse.status_code == 404


def test_l_api_est_servie_sous_le_certificat_fourni(certificat_fourni):
    ca, _ = certificat_fourni

    reponse = httpx.get(f"{URL_SITE}/api/moi", verify=ssl.create_default_context(cadata=ca))

    assert reponse.status_code == 401


def test_certificat_fourni_manquant_web_ne_demarre_pas(tmp_path: Path):
    (tmp_path / "certificat.crt").write_text("")
    try:
        with pytest.raises(subprocess.CalledProcessError):
            recreer_le_site(tmp_path)

        journal = compose("logs", "--no-log-prefix", "certificats").stdout
        assert f"ARGOS_CERTIFICAT_DOSSIER ({tmp_path}) : certificat.crt manquant, vide ou illisible par l'utilisateur 101." in journal
        assert compose("ps", "-q", "--status", "running", "web").stdout.strip() == ""
    finally:
        recreer_le_site()
        attendre_api()
