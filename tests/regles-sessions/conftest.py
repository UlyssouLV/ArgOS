"""Fixtures : l'application montée en processus, horloge et configuration injectées, PostgreSQL de test.

Seam étroit, réservé aux règles impossibles à tester vite en HTTP (temps, configuration).
Le reste de l'API se teste en HTTP contre la stack (tests/api/).
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from testcontainers.community.postgres import PostgresContainer

from argos_api.app import creer_app
from argos_api.configuration import Configuration

REPO_ROOT = Path(__file__).resolve().parents[2]
DOSSIER_API = REPO_ROOT / "api"
# Même image que le service db de compose.yaml.
IMAGE_POSTGRES = "postgres:18.6-alpine3.24"

IDENTIFIANT = "administrateur"
MOT_DE_PASSE = "une phrase de passe assez longue"


class HorlogeFigee:
    """Horloge qui n'avance que quand le test le décide."""

    def __init__(self) -> None:
        self.maintenant = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.maintenant

    def avancer(self, **duree: float) -> None:
        self.maintenant += timedelta(**duree)


@pytest.fixture(scope="session")
def url_base() -> Iterator[str]:
    with PostgresContainer(IMAGE_POSTGRES, driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        # Le schéma vient des migrations, comme au démarrage du conteneur api.
        config = Config(str(DOSSIER_API / "alembic.ini"))
        config.set_main_option("script_location", str(DOSSIER_API / "migrations"))
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("ARGOS_URL_BASE", url)
            command.upgrade(config, "head")
        yield url


@pytest.fixture(autouse=True)
def base_vide(url_base: str) -> None:
    moteur = create_engine(url_base)
    with moteur.begin() as connexion:
        connexion.execute(text("TRUNCATE sessions"))
    moteur.dispose()


@pytest.fixture
def horloge() -> HorlogeFigee:
    return HorlogeFigee()


@pytest.fixture
def demarrer(url_base: str, horloge: HorlogeFigee) -> Callable[..., TestClient]:
    """Démarre l'application (un « redémarrage » si on l'appelle de nouveau), sur la même base."""

    def _demarrer(mot_de_passe: str = MOT_DE_PASSE) -> TestClient:
        configuration = Configuration(
            ARGOS_IDENTIFIANT=IDENTIFIANT,
            ARGOS_MOT_DE_PASSE=mot_de_passe,
            ARGOS_URL_BASE=url_base,
        )
        return TestClient(creer_app(configuration, horloge))

    return _demarrer


@pytest.fixture
def client(demarrer) -> TestClient:
    return demarrer()


def se_connecter(client: TestClient, mot_de_passe: str = MOT_DE_PASSE):
    return client.post(
        "/api/session",
        json={"identifiant": IDENTIFIANT, "mot_de_passe": mot_de_passe},
    )
