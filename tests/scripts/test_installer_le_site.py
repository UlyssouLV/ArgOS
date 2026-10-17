"""Installation Ubuntu : le Site dans un préfixe factice, sans clone ni simulation."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "installer-le-site.sh"
DELAI_S = 10


@dataclass
class Resultat:
    code: int
    sortie: str
    racine: Path
    unite: Path
    useradd: list[str]
    usermod: list[str]
    systemctl: list[str]


class Ubuntu:
    """Hôte d'installation simulé : préfixe, compte, systemd et Docker via le PATH."""

    def __init__(self, dossier: Path) -> None:
        self.prefixe = dossier / "prefixe"
        self.prefixe.mkdir()
        self.racine = self.prefixe / "opt" / "argos"
        self.unite = self.prefixe / "etc" / "systemd" / "system" / "argos.service"
        self.bin = dossier / "bin"
        self.bin.mkdir()
        self.journal_useradd = dossier / "useradd.txt"
        self.journal_usermod = dossier / "usermod.txt"
        self.journal_systemctl = dossier / "systemctl.txt"
        self._commande("docker", "exit 0")
        self._commande("chown", "exit 0")
        self._commande(
            "getent",
            'if [ "$1" = group ] && [ "$2" = docker ]; then exit 0; fi; exit 1',
        )
        self._commande("useradd", f'echo "$*" >> "{self.journal_useradd}"')
        self._commande("usermod", f'echo "$*" >> "{self.journal_usermod}"')
        self._commande("systemctl", f'echo "$*" >> "{self.journal_systemctl}"')

    def installer(self) -> Resultat:
        env = os.environ | {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "ARGOS_PREFIX": str(self.prefixe),
            "ARGOS_IDENTIFIANT": "administrateur",
            "ARGOS_MOT_DE_PASSE": "secret",
        }
        proc = subprocess.run(
            ["bash", str(SCRIPT)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            timeout=DELAI_S,
        )
        return Resultat(
            proc.returncode,
            proc.stdout + proc.stderr,
            self.racine,
            self.unite,
            self._lignes(self.journal_useradd),
            self._lignes(self.journal_usermod),
            self._lignes(self.journal_systemctl),
        )

    def _commande(self, nom: str, corps: str) -> None:
        chemin = self.bin / nom
        chemin.write_text(f"#!/bin/sh\n{corps}\n")
        chemin.chmod(0o755)

    @staticmethod
    def _lignes(chemin: Path) -> list[str]:
        return chemin.read_text().splitlines() if chemin.exists() else []


@pytest.fixture
def ubuntu(tmp_path: Path) -> Ubuntu:
    return Ubuntu(tmp_path)


def test_le_dossier_du_site_a_le_compose_lenv_et_la_detection_sans_sources_ni_sonar(ubuntu):
    resultat = ubuntu.installer()

    assert resultat.code == 0, resultat.sortie
    assert (resultat.racine / "compose.yaml").is_file()
    assert (resultat.racine / ".env").is_file()
    assert (resultat.racine / "scripts" / "cameras" / "configurer-detection.sh").is_file()
    assert not (resultat.racine / "api").exists()
    assert not (resultat.racine / "web").exists()
    assert not (resultat.racine / "compose.simulation.yaml").exists()
    env = (resultat.racine / ".env").read_text()
    assert "SONAR_" not in env
    assert "ARGOS_VERSION=" in env


def test_compte_argos_dans_le_groupe_docker_et_unite_activee_au_boot(ubuntu):
    resultat = ubuntu.installer()

    assert resultat.code == 0, resultat.sortie
    assert any("argos" in ligne for ligne in resultat.useradd)
    assert any("-aG docker" in ligne and "argos" in ligne for ligne in resultat.usermod)
    assert any("enable --now" in ligne and "argos.service" in ligne for ligne in resultat.systemctl)
    texte = resultat.unite.read_text()
    assert "After=docker.service network-online.target" in texte
    assert "WantedBy=multi-user.target" in texte
    assert "Restart=on-failure" in texte
    assert "User=argos" in texte
    assert "WorkingDirectory=/opt/argos" in texte


def test_compose_up_sans_build_ni_simulation_et_conteneurs_unless_stopped(ubuntu):
    resultat = ubuntu.installer()

    assert resultat.code == 0, resultat.sortie
    texte = resultat.unite.read_text()
    assert "docker compose up" in texte
    assert "--build" not in texte
    assert "compose.simulation.yaml" not in texte
    compose = (resultat.racine / "compose.yaml").read_text()
    assert "restart: unless-stopped" in compose
    assert not (resultat.racine / "compose.simulation.yaml").exists()
