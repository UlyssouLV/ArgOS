"""Lanceur Mac `lancer-argos.command` : UI en HTTPS et Autorité du Site au trousseau de session.

Le lanceur et ses scripts sont copiés dans un dossier temporaire (il écrit `.env` à côté de lui). Les
commandes du Mac sont simulées (PATH) : `docker` (stack prête), `osascript`, `open` (adresses notées),
`curl` (sert l'Autorité du Site, ou 404 en mode certificat fourni), `security` (trousseau simulé, ajouts
notés), `uname` et `ifconfig` (une seule prise : la Détection ne pose pas de question).
"""

import os
import select
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from conftest import ifconfig_macos

REPO_ROOT = Path(__file__).resolve().parents[2]
DELAI_S = 20
QUESTION = "Ajouter l'Autorité du Site au trousseau"


@dataclass
class Resultat:
    code: int
    sortie: str
    ouvertes: list[str]
    ajouts: list[str]


def autorite_du_site() -> x509.Certificate:
    cle = ec.generate_private_key(ec.SECP256R1())
    nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Autorité du Site ArgOS")])
    maintenant = datetime.now(UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(nom)
        .issuer_name(nom)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant)
        .not_valid_after(maintenant + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(cle, hashes.SHA256())
    )


def empreinte(cert: x509.Certificate) -> str:
    """Forme affichée : octets hexadécimaux en majuscules séparés par « : »."""
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


class Mac:
    """Mac hôte simulé, stack démarrée."""

    def __init__(self, dossier: Path) -> None:
        self.depot = dossier / "depot"
        self.depot.mkdir()
        shutil.copy2(REPO_ROOT / "lancer-argos.command", self.depot)
        shutil.copy2(REPO_ROOT / ".env.example", self.depot)
        shutil.copytree(REPO_ROOT / "scripts", self.depot / "scripts")
        (self.depot / ".env").write_text("ARGOS_IDENTIFIANT=administrateur\nARGOS_MOT_DE_PASSE=secret\n")
        self.home = dossier / "home"
        self.home.mkdir()
        self.bin = dossier / "bin"
        self.bin.mkdir()
        self.ouvertes = dossier / "ouvertes.txt"
        self.ajouts = dossier / "ajouts.txt"
        self.autorite_servie = dossier / "argos-ca.crt"
        self.trousseau = dossier / "trousseau.txt"
        self.trousseau.write_text("")

        self._commande("uname", "echo Darwin")
        self._commande("ifconfig", f"cat <<'FIN'\n{ifconfig_macos(('en0', '192.168.1.23', '0xffffff00'))}FIN")
        self._commande("docker", "exit 0")
        self._commande("osascript", "cat >/dev/null")
        self._commande("open", f'echo "$*" >> "{self.ouvertes}"')
        # Seule l'adresse de l'Autorité sur le port HTTP local est servie ; absente : 404 (curl -f : code 22).
        self._commande(
            "curl",
            f'for a in "$@"; do case "$a" in http://localhost*/argos-ca.crt) '
            f'[ -f "{self.autorite_servie}" ] || exit 22; cat "{self.autorite_servie}"; exit 0;; esac; done; exit 7',
        )
        self._commande(
            "security",
            f'case "$1" in find-certificate) cat "{self.trousseau}";; '
            f'add-trusted-cert) echo "$*" >> "{self.ajouts}";; *) exit 1;; esac',
        )

    def sert(self, autorite: x509.Certificate) -> None:
        self.autorite_servie.write_bytes(autorite.public_bytes(serialization.Encoding.PEM))

    def deja_au_trousseau(self, autorite: x509.Certificate) -> None:
        """Sortie de `security find-certificate -a -Z` : empreinte SHA-256 en hexadécimal, sans séparateur."""
        self.trousseau.write_text(
            f"SHA-256 hash: {autorite.fingerprint(hashes.SHA256()).hex().upper()}\n"
            f'keychain: "{self.home}/Library/Keychains/login.keychain-db"\n'
        )

    def lancer(self, reponses: str = "") -> Resultat:
        env = os.environ | {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(self.home)}
        maitre, esclave = os.openpty()
        fini = threading.Event()

        def touches_de_fin() -> None:
            # La pause de fin (`read -n 1`) passe la ligne en mode brut et ne voit pas une touche tapée
            # d'avance : on en tape une à intervalles, après les réponses, jusqu'à la fin du lanceur. L'écho
            # du terminal est lu au passage : sous macOS, un écho jamais lu bloque la lecture.
            while not fini.is_set():
                pret, _, _ = select.select([maitre], [], [], 0.2)
                if pret:
                    os.read(maitre, 1024)
                else:
                    os.write(maitre, b"\n")

        try:
            os.write(maitre, reponses.encode())
            tapeur = threading.Thread(target=touches_de_fin, daemon=True)
            tapeur.start()
            proc = subprocess.run(
                ["bash", str(self.depot / "lancer-argos.command")],
                stdin=esclave,
                capture_output=True,
                text=True,
                env=env,
                timeout=DELAI_S,
            )
        finally:
            fini.set()
            tapeur.join()
            os.close(esclave)
            os.close(maitre)
        return Resultat(proc.returncode, proc.stdout + proc.stderr, self._lignes(self.ouvertes), self._lignes(self.ajouts))

    @staticmethod
    def _lignes(chemin: Path) -> list[str]:
        return chemin.read_text().splitlines() if chemin.exists() else []

    def _commande(self, nom: str, corps: str) -> None:
        chemin = self.bin / nom
        chemin.write_text(f"#!/bin/sh\n{corps}\n")
        chemin.chmod(0o755)


@pytest.fixture
def mac(tmp_path: Path) -> Mac:
    return Mac(tmp_path)


def test_l_ui_ouverte_est_https_localhost(mac):
    mac.sert(autorite := autorite_du_site())
    mac.deja_au_trousseau(autorite)

    resultat = mac.lancer()

    assert resultat.code == 0, resultat.sortie
    assert resultat.ouvertes == ["https://localhost"]
    assert "http://localhost:8080" not in resultat.sortie


def test_l_empreinte_affichee_est_celle_de_l_autorite_servie(mac):
    mac.sert(autorite := autorite_du_site())
    mac.deja_au_trousseau(autorite)

    resultat = mac.lancer()

    assert resultat.code == 0, resultat.sortie
    assert empreinte(autorite) in resultat.sortie


def test_autorite_absente_du_trousseau_refusee_rien_d_installe_et_le_lanceur_continue(mac):
    mac.sert(autorite_du_site())

    resultat = mac.lancer("n\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION in resultat.sortie
    assert resultat.ajouts == []
    assert resultat.ouvertes == ["https://localhost"]


def test_autorite_absente_du_trousseau_acceptee_ajoutee_comme_racine_de_confiance(mac):
    mac.sert(autorite_du_site())

    resultat = mac.lancer("o\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION in resultat.sortie
    assert len(resultat.ajouts) == 1
    ajout = resultat.ajouts[0].split()
    assert ajout[0] == "add-trusted-cert"
    assert ajout[ajout.index("-r") + 1] == "trustRoot"
    assert ajout[ajout.index("-k") + 1] == f"{mac.home}/Library/Keychains/login.keychain-db"
    assert resultat.ouvertes == ["https://localhost"]


def test_autorite_deja_au_trousseau_aucune_question(mac):
    mac.sert(autorite := autorite_du_site())
    mac.deja_au_trousseau(autorite)

    resultat = mac.lancer()

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert resultat.ajouts == []


def test_certificat_fourni_rien_a_installer(mac):
    # Mode certificat fourni : /argos-ca.crt répond 404.

    resultat = mac.lancer()

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert resultat.ajouts == []
    assert resultat.ouvertes == ["https://localhost"]
