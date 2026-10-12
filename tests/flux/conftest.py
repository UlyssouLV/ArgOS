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
# Chemins de vraies caméras : style Hikvision, style Dahua (requête comprise), chemin exotique.
CHEMINS = {
    "camera-simulee-1": "Streaming/Channels/101",
    "camera-simulee-2": "cam/realmonitor?channel=1&subtype=0",
    "camera-simulee-3": "flux",
}
# Identifiants de dev de camera-simulee-2 (media/simulated/README.md).
IDENTIFIANTS = {"camera-simulee-2": "admin:argos-simulee"}
# Adresses fixes des Caméras simulées sur leur réseau (media/simulated/README.md).
IPS = {"camera-simulee-1": "172.30.0.11", "camera-simulee-2": "172.30.0.12", "camera-simulee-3": "172.30.0.13"}
MACS = {
    "camera-simulee-1": "02:a6:05:00:00:01",
    "camera-simulee-2": "02:a6:05:00:00:02",
    "camera-simulee-3": "02:a6:05:00:00:03",
}


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
