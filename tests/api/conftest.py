"""Fixtures de session : la stack Docker Compose tourne et l'API du Site répond."""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stack_compose import (  # noqa: E402
    URL_API,
    attendre_api,
    compose,
    identifiants_administrateur,
    lancer_stack,
)

__all__ = ["URL_API", "attendre_api", "compose"]


@pytest.fixture(scope="session")
def administrateur() -> dict[str, str]:
    return identifiants_administrateur()


@pytest.fixture(scope="session", autouse=True)
def stack(administrateur):
    lancer_stack()


@pytest.fixture
def client():
    with httpx.Client(base_url=URL_API, timeout=10) as c:
        yield c
