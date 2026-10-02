"""Fixtures : le script de configuration de la Détection lancé avec une fausse commande réseau.

Les commandes `uname`, `ip` et `ifconfig` sont remplacées (PATH) par des scripts qui renvoient
une sortie préenregistrée ; le `.env` est un fichier temporaire.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "cameras" / "configurer-detection.sh"
DELAI_S = 10

QUESTION = "Quelle(s) prise(s)"


@dataclass
class Resultat:
    code: int
    sortie: str
    env: dict[str, str]


class Machine:
    """Machine hôte simulée : système, prises réseau et `.env`."""

    def __init__(self, dossier: Path) -> None:
        self.bin = dossier / "bin"
        self.bin.mkdir()
        self.sortie_reseau = dossier / "sortie-reseau.txt"
        self.fichier_env = dossier / ".env"
        self.fichier_env.write_text("ARGOS_IDENTIFIANT=administrateur\n")

    def systeme(self, nom: str, sortie_reseau: str) -> None:
        """`nom` : Linux (sortie de `ip -o -4 addr show`) ou Darwin (sortie de `ifconfig`)."""
        self._commande("uname", f"echo {nom}")
        commande = "ip" if nom == "Linux" else "ifconfig"
        self._commande(commande, f'cat "{self.sortie_reseau}"')
        self.sortie_reseau.write_text(sortie_reseau)

    def ecrire_env(self, contenu: str) -> None:
        self.fichier_env.write_text(contenu)

    def lancer(self, *, terminal: bool, reponses: str = "") -> Resultat:
        env = os.environ | {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "ARGOS_FICHIER_ENV": str(self.fichier_env),
        }
        if terminal:
            maitre, esclave = os.openpty()
            try:
                os.write(maitre, reponses.encode())
                proc = subprocess.run(
                    ["bash", str(SCRIPT)], stdin=esclave, capture_output=True, text=True, env=env, timeout=DELAI_S
                )
            finally:
                os.close(esclave)
                os.close(maitre)
        else:
            proc = subprocess.run(
                ["bash", str(SCRIPT)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env=env,
                timeout=DELAI_S,
            )
        return Resultat(proc.returncode, proc.stdout + proc.stderr, self.lire_env())

    def lire_env(self) -> dict[str, str]:
        valeurs = {}
        for ligne in self.fichier_env.read_text().splitlines():
            if "=" in ligne and not ligne.startswith("#"):
                cle, valeur = ligne.split("=", 1)
                valeurs[cle] = valeur
        return valeurs

    def _commande(self, nom: str, corps: str) -> None:
        chemin = self.bin / nom
        chemin.write_text(f"#!/bin/sh\n{corps}\n")
        chemin.chmod(0o755)


@pytest.fixture
def machine(tmp_path: Path) -> Machine:
    return Machine(tmp_path)


def ip_linux(*prises: tuple[str, str]) -> str:
    """Sortie de `ip -o -4 addr show` pour des prises (nom, adresse/préfixe)."""
    return "".join(
        f"{n}: {nom}    inet {adresse} scope global {nom}\\       valid_lft forever preferred_lft forever\n"
        for n, (nom, adresse) in enumerate(prises, start=1)
    )


def ifconfig_macos(*prises: tuple[str, str, str]) -> str:
    """Sortie de `ifconfig` pour des prises (nom, adresse, masque hexadécimal)."""
    return "".join(
        f"{nom}: flags=8863<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n"
        f"\tether aa:bb:cc:dd:ee:0{n}\n"
        f"\tinet {adresse} netmask {masque} broadcast 255.255.255.255\n"
        "\tstatus: active\n"
        for n, (nom, adresse, masque) in enumerate(prises, start=1)
    )
