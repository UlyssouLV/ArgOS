"""Lecture de `roles.test-roots.paths` pour le script CI."""

import importlib.util
from pathlib import Path

from conftest import REPO_ROOT

_SPEC = importlib.util.spec_from_file_location(
    "lire_test_roots", REPO_ROOT / "scripts" / "lire_test_roots.py"
)
_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)
lire_test_roots = _MOD.lire_test_roots


def test_lire_test_roots_sur_le_fichier_du_depot():
    chemins = lire_test_roots(REPO_ROOT / "agents" / "roles.yml")

    assert "tests/scripts/" in chemins
    assert "tests/web/" in chemins
    assert chemins.index("tests/flux/") < chemins.index("simulation/onvif/")


def test_lire_test_roots_ignore_les_autres_roles_et_les_commentaires(tmp_path: Path):
    roles = tmp_path / "roles.yml"
    roles.write_text(
        "# entête\n"
        "roles:\n"
        "  glossary:\n"
        "    paths:\n"
        "      - docs/glossaire.md\n"
        "  test-roots:\n"
        "    paths:\n"
        "      - tests/alpha/\n"
        "      # ignoré\n"
        "      - 'tests/beta/'\n"
        "  adr:\n"
        "    paths:\n"
        "      - docs/adr/\n"
    )

    assert lire_test_roots(roles) == ["tests/alpha/", "tests/beta/"]
