"""Fixtures de session : la stack Docker Compose tourne, l'UI et l'API du Site répondent."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stack_compose import attendre, identifiants_administrateur, lancer_stack, redemarrer_api  # noqa: E402

__all__ = ["redemarrer_api"]

URL_UI = "http://localhost:8080"


@pytest.fixture(scope="session")
def administrateur() -> dict[str, str]:
    return identifiants_administrateur()


@pytest.fixture(scope="session", autouse=True)
def stack(administrateur):
    lancer_stack()
    attendre(URL_UI)
