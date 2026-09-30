"""Fixture de session : la stack Docker Compose tourne et les Caméras simulées sont prêtes."""

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOTE = "localhost"
PORT_RTSP = 8554
PORT_HLS = 8888
CAMERAS_SIMULEES = ["cam1", "cam2", "cam3"]
DELAI_PRET_S = 60


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def _stack_tourne() -> bool:
    return bool(_compose("ps", "--status", "running", "--quiet").stdout.strip())


def _playlist_hls_repond(camera: str) -> bool:
    url = f"http://{HOTE}:{PORT_HLS}/{camera}/index.m3u8"
    try:
        with urllib.request.urlopen(url, timeout=10) as reponse:
            return reponse.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False


@pytest.fixture(scope="session", autouse=True)
def stack():
    if not _stack_tourne():
        _compose("up", "-d", "--wait")
    echeance = time.monotonic() + DELAI_PRET_S
    for camera in CAMERAS_SIMULEES:
        while not _playlist_hls_repond(camera):
            if time.monotonic() > echeance:
                pytest.fail(f"Caméra simulée {camera} pas prête après {DELAI_PRET_S} s")
            time.sleep(1)
