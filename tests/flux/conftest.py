"""Fixture de session : la stack Docker Compose tourne avec la simulation, Caméras simulées prêtes."""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FICHIER_PROD = "compose.yaml"
FICHIER_SIMULATION = "compose.simulation.yaml"
RESEAU_SIMULATION = "cameras-simulees"
SOUS_RESEAU_SIMULATION = "172.30.0.0/24"
CAMERAS_SIMULEES = [f"camera-simulee-{n}" for n in range(1, 7)]
# Chemins de vraies caméras : style Hikvision, style Dahua (requête comprise), chemin exotique, Hikvision en H.265,
# Hikvision, Hikvision en H.265 (audio en avance, comme Cam 01).
CHEMINS = {
    "camera-simulee-1": "Streaming/Channels/101",
    "camera-simulee-2": "cam/realmonitor?channel=1&subtype=0",
    "camera-simulee-3": "flux",
    "camera-simulee-4": "Streaming/Channels/101",
    "camera-simulee-5": "Streaming/Channels/101",
    "camera-simulee-6": "Streaming/Channels/101",
}
# Codec diffusé, tel que nommé par ffprobe : camera-simulee-4 et camera-simulee-6 en H.265 (HEVC), les autres en H.264.
CAMERAS_H265 = ("camera-simulee-4", "camera-simulee-6")
CODECS = {camera: "hevc" if camera in CAMERAS_H265 else "h264" for camera in CAMERAS_SIMULEES}
# Piste audio annoncée (codec, fréquence, canaux) : PCM 16 bits pour la 4 (bug #141), G.711 µ-law pour la 6 (Cam 01).
AUDIOS = {"camera-simulee-4": ("pcm_s16be", "8000", 1), "camera-simulee-6": ("pcm_mulaw", "8000", 1)}
# Identifiants de dev de camera-simulee-2 (media/simulated/README.md).
IDENTIFIANTS = {"camera-simulee-2": "admin:argos-simulee"}
# Adresses fixes des Caméras simulées sur leur réseau (media/simulated/README.md).
IPS = {
    "camera-simulee-1": "172.30.0.11",
    "camera-simulee-2": "172.30.0.12",
    "camera-simulee-3": "172.30.0.13",
    "camera-simulee-4": "172.30.0.14",
    "camera-simulee-5": "172.30.0.15",
    "camera-simulee-6": "172.30.0.16",
}
MACS = {
    "camera-simulee-1": "02:a6:05:00:00:01",
    "camera-simulee-2": "02:a6:05:00:00:02",
    "camera-simulee-3": "02:a6:05:00:00:03",
    "camera-simulee-4": "02:a6:05:00:00:04",
    "camera-simulee-5": "02:a6:05:00:00:05",
    "camera-simulee-6": "02:a6:05:00:00:06",
}


def compose(
    *args: str, fichiers: tuple[str, ...] = (FICHIER_PROD, FICHIER_SIMULATION), env: dict[str, str] | None = None
) -> str:
    """`env` : variables de plus, lues par l'interpolation des fichiers compose."""
    options = [option for fichier in fichiers for option in ("-f", fichier)]
    return subprocess.run(
        ["docker", "compose", *options, *args],
        cwd=REPO_ROOT,
        env=os.environ | (env or {}),
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
    # --build --wait : images du clone (dont le Pont) ; Caméras simulées « healthy » une fois la vidéo diffusée.
    compose("up", "-d", "--build", "--wait")
