"""Outils communs aux racines de tests qui tournent contre la stack Docker Compose lancée.

Importé par les `conftest.py` de `tests/api/` et `tests/web/` (sans dépendance : stdlib, pytest, httpx).
"""

import subprocess
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def _repond(url: str) -> bool:
    try:
        return httpx.get(url, timeout=5).status_code == 200
    except httpx.TransportError:
        return False


def attendre(url: str) -> None:
    echeance = time.monotonic() + DELAI_PRET_S
    while not _repond(url):
        if time.monotonic() > echeance:
            pytest.fail(f"{url} ne répond pas après {DELAI_PRET_S} s")
        time.sleep(1)


def attendre_api() -> None:
    attendre(f"{URL_API}/api/docs")


def redemarrer_api() -> None:
    compose("restart", "api")
    attendre_api()


def identifiants_administrateur() -> dict[str, str]:
    """Lus dans `.env` ; s'ils manquent, échec immédiat qui dit quoi ajouter."""
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


def lancer_stack() -> None:
    # --build : les tests visent toujours le code courant, pas une image périmée.
    compose("up", "-d", "--build", "--wait")
    attendre_api()
