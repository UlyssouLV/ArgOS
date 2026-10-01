"""Fixtures de session : la stack Docker Compose tourne et l'API du Site répond."""

import subprocess
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
URL_API = "http://localhost:8000"
DELAI_PRET_S = 120
CLES_ADMINISTRATEUR = ("ARGOS_IDENTIFIANT", "ARGOS_MOT_DE_PASSE")


def compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def _lire_env() -> dict[str, str]:
    chemin = REPO_ROOT / ".env"
    if not chemin.exists():
        return {}
    valeurs = {}
    for ligne in chemin.read_text().splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            valeurs[cle.strip()] = valeur.strip().strip("\"'")
    return valeurs


def _api_repond() -> bool:
    try:
        return httpx.get(f"{URL_API}/api/docs", timeout=5).status_code == 200
    except httpx.TransportError:
        return False


def attendre_api() -> None:
    echeance = time.monotonic() + DELAI_PRET_S
    while not _api_repond():
        if time.monotonic() > echeance:
            pytest.fail(f"L'API ne répond pas sur {URL_API} après {DELAI_PRET_S} s")
        time.sleep(1)


@pytest.fixture(scope="session")
def administrateur() -> dict[str, str]:
    env = _lire_env()
    manquantes = [cle for cle in CLES_ADMINISTRATEUR if not env.get(cle)]
    if manquantes:
        pytest.fail(
            "Identifiants de l'Administrateur absents de .env : ajouter "
            + ", ".join(f"{cle}=…" for cle in manquantes)
            + " (voir .env.example), puis relancer.",
            pytrace=False,
        )
    return {
        "identifiant": env["ARGOS_IDENTIFIANT"],
        "mot_de_passe": env["ARGOS_MOT_DE_PASSE"],
    }


@pytest.fixture(scope="session", autouse=True)
def stack(administrateur):
    # --build : les tests visent toujours le code courant de api/, pas une image périmée.
    compose("up", "-d", "--build", "--wait")
    attendre_api()


@pytest.fixture
def client():
    with httpx.Client(base_url=URL_API, timeout=10) as c:
        yield c
