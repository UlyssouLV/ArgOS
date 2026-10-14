"""Fixtures de session : la stack Docker Compose tourne, l'UI et l'API du Site répondent en HTTPS."""

import base64
import hashlib
import os
import sys
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stack_compose import (  # noqa: E402
    URL_SITE,
    attendre,
    autorite_du_site,
    certificat_presente,
    identifiants_administrateur,
    lancer_stack,
    redemarrer_api,
)

__all__ = ["redemarrer_api"]


@pytest.fixture(scope="session")
def administrateur() -> dict[str, str]:
    return identifiants_administrateur()


@pytest.fixture(scope="session", autouse=True)
def stack(administrateur, tmp_path_factory):
    lancer_stack()
    attendre(URL_SITE)
    # Les requêtes que Playwright fait lui-même (route.fetch) partent de son pilote Node, lancé après :
    # il fait confiance à l'Autorité du Site.
    autorite = tmp_path_factory.mktemp("autorite") / "argos-ca.crt"
    autorite.write_text(autorite_du_site())
    os.environ["NODE_EXTRA_CA_CERTS"] = str(autorite)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, stack):
    """Chromium fait confiance au certificat serveur que l'Autorité du Site vient de valider, et à lui seul.

    Comme un poste qui a installé l'Autorité, sans toucher au trousseau de la machine de test.
    """
    cle = x509.load_der_x509_certificate(certificat_presente()).public_key()
    spki = cle.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    empreinte = base64.b64encode(hashlib.sha256(spki).digest()).decode()
    return {
        **browser_type_launch_args,
        "args": [*browser_type_launch_args.get("args", []), f"--ignore-certificate-errors-spki-list={empreinte}"],
    }
