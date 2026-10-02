"""Outils communs aux racines de tests qui tournent contre la stack Docker Compose lancée.

Importé par les `conftest.py` de `tests/api/` et `tests/web/` (sans dépendance : stdlib, pytest, httpx).
"""

import subprocess
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# La stack des tests porte la simulation : Caméras simulées superposées à la stack de prod.
FICHIERS_COMPOSE = ("compose.yaml", "compose.simulation.yaml")
URL_API = "http://localhost:8000"
DELAI_PRET_S = 120
CLES_ADMINISTRATEUR = ("ARGOS_IDENTIFIANT", "ARGOS_MOT_DE_PASSE")
# Identifiants de dev de camera-simulee-2 (media/simulated/README.md).
IDENTIFIANTS_SIMULES = {2: "admin:argos-simulee"}


def compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *(option for fichier in FICHIERS_COMPOSE for option in ("-f", fichier)), *args],
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


def url_camera_simulee(numero: int, chemin: str, requete: str, identifiants: bool = True) -> str:
    """URL d'une Caméra simulée, vue de `api` et du pont ; `identifiants` ne joue que pour camera-simulee-2.

    La requête rend l'URL unique (l'URL est unique parmi les Caméras) ; la Caméra simulée l'ignore.
    """
    utilisateur = f"{IDENTIFIANTS_SIMULES[numero]}@" if identifiants and numero in IDENTIFIANTS_SIMULES else ""
    return f"rtsp://{utilisateur}camera-simulee-{numero}/{chemin}?test={requete}"


def adresses_ip(service: str) -> set[str]:
    """Adresses IPv4 du conteneur d'un service, sur tous ses réseaux Compose."""
    conteneur = compose("ps", "-q", service).stdout.strip()
    inspection = subprocess.run(
        ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", conteneur],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(inspection.stdout.split())


def lancer_stack() -> None:
    # --build : les tests visent toujours le code courant, pas une image périmée.
    compose("up", "-d", "--build", "--wait")
    attendre_api()
