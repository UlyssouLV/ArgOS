"""Fixture de session : la stack Docker Compose tourne avec la simulation, Caméras simulées prêtes."""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FICHIER_PROD = "compose.yaml"
FICHIER_SIMULATION = "compose.simulation.yaml"
RESEAU_SIMULATION = "cameras-simulees"
SOUS_RESEAU_SIMULATION = "172.30.0.0/24"
CAMERAS_SIMULEES = ["camera-simulee-1", "camera-simulee-2", "camera-simulee-3"]
CHEMIN = "flux"
# Identifiants de dev de camera-simulee-2 (media/simulated/README.md).
IDENTIFIANTS = {"camera-simulee-2": "admin:argos-simulee"}


def compose(*args: str, fichiers: tuple[str, ...] = (FICHIER_PROD, FICHIER_SIMULATION)) -> str:
    options = [option for fichier in fichiers for option in ("-f", fichier)]
    return subprocess.run(
        ["docker", "compose", *options, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def configuration(*fichiers: str) -> dict:
    return json.loads(compose("config", "--format", "json", fichiers=fichiers))


@pytest.fixture(scope="session")
def reseau_simulation() -> str:
    """Nom Docker du réseau des Caméras simulées (préfixé par le projet Compose)."""
    return configuration(FICHIER_PROD, FICHIER_SIMULATION)["networks"][RESEAU_SIMULATION]["name"]


@pytest.fixture(scope="session", autouse=True)
def stack():
    # --wait : les Caméras simulées sont « healthy » quand leur vidéo est diffusée.
    compose("up", "-d", "--wait")
