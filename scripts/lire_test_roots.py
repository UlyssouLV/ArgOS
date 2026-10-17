#!/usr/bin/env python3
"""Lit `roles.test-roots.paths` dans `agents/roles.yml` (un chemin par ligne)."""

from __future__ import annotations

import re
from pathlib import Path

_BLOC_PATHS = re.compile(
    r"(?m)^  test-roots:\n(?:    .*\n)*?    paths:\n((?:      - .*\n?)*)"
)


def _sans_commentaires(texte: str) -> str:
    return "\n".join(
        ligne
        for ligne in texte.splitlines()
        if ligne.strip() and not ligne.lstrip().startswith("#")
    )


def _chemins_du_bloc(bloc: str) -> list[str]:
    chemins: list[str] = []
    for ligne in bloc.splitlines():
        cle = ligne.strip()
        if cle.startswith("- "):
            chemins.append(cle[2:].strip().strip("'\""))
    return chemins


def lire_test_roots(roles_yml: Path) -> list[str]:
    """Retourne les chemins de `roles.test-roots.paths` (ordre du fichier)."""
    texte = _sans_commentaires(roles_yml.read_text(encoding="utf-8"))
    if not texte.endswith("\n"):
        texte += "\n"
    match = _BLOC_PATHS.search(texte)
    if match is None:
        return []
    return _chemins_du_bloc(match.group(1))


def main() -> None:
    # Chemin fixé au dépôt du script (pas d'argument CLI : évite le path traversal).
    chemin = Path(__file__).resolve().parent.parent / "agents" / "roles.yml"
    for racine in lire_test_roots(chemin):
        print(racine)


if __name__ == "__main__":
    main()
