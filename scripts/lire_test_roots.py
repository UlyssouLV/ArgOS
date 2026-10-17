#!/usr/bin/env python3
"""Lit `roles.test-roots.paths` dans `agents/roles.yml` (un chemin par ligne)."""

from __future__ import annotations

import sys
from pathlib import Path


def lire_test_roots(roles_yml: Path) -> list[str]:
    """Retourne les chemins de `roles.test-roots.paths` (ordre du fichier)."""
    dans_roles = False
    dans_test_roots = False
    dans_paths = False
    chemins: list[str] = []

    for ligne in roles_yml.read_text(encoding="utf-8").splitlines():
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue

        indent = len(ligne) - len(ligne.lstrip(" "))
        cle = ligne.strip()

        if indent == 0 and cle == "roles:":
            dans_roles = True
            dans_test_roots = False
            dans_paths = False
            continue

        if not dans_roles:
            continue

        if indent == 2 and cle.endswith(":") and not cle.startswith("-"):
            dans_test_roots = cle == "test-roots:"
            dans_paths = False
            continue

        if dans_test_roots and indent == 4 and cle == "paths:":
            dans_paths = True
            continue

        if dans_paths:
            if indent == 6 and cle.startswith("- "):
                chemins.append(cle[2:].strip().strip("'\""))
                continue
            if indent <= 4:
                break

    return chemins


def main() -> None:
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("agents/roles.yml")
    for racine in lire_test_roots(chemin):
        print(racine)


if __name__ == "__main__":
    main()
