"""Script CI (`/t -a`) : `.env` d’exemple, stack avec simulation, pytest par racine `test-roots`."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "lancer-les-tests.sh"
DELAI_S = 15
COMPTE = "administrateur"
PHRASE = "argos-dev-phrase-de-passe-de-test"


@dataclass
class Resultat:
    code: int
    sortie: str
    env: dict[str, str]
    journal: list[str]


class Depot:
    """Clone factice : commandes hôte simulées, `.env` et racines de tests contrôlées."""

    def __init__(self, dossier: Path, *, avec_uv: bool = True) -> None:
        self.depot = dossier / "depot"
        self.depot.mkdir()
        self.bin = dossier / "bin"
        self.bin.mkdir()
        self.home = dossier / "home"
        self.home.mkdir()
        self.journal = dossier / "journal.txt"
        self.journal.write_text("")
        self.avec_uv = avec_uv
        (self.depot / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.depot / "scripts" / "lancer-les-tests.sh")
        (self.depot / ".env.example").write_text(
            "ARGOS_VERSION=0.7.0\nARGOS_IDENTIFIANT=\nARGOS_MOT_DE_PASSE=\nSONAR_TOKEN=\n"
        )
        (self.depot / "compose.yaml").write_text("services: {}\n")
        (self.depot / "compose.simulation.yaml").write_text("services: {}\n")
        self.ecrire_roles(["tests/alpha/", "tests/beta/"])
        self._racine("tests/alpha")
        self._racine("tests/beta")
        python_stub = dossier / "python-stub"
        python_stub.write_text(
            "#!/bin/sh\n"
            f'echo python $* cwd=$(pwd) >> "{self.journal}"\n'
            'if [ -n "$FAIL_RACINE" ]; then case "$(pwd)" in *"$FAIL_RACINE"*) exit 1;; esac; fi\n'
            "exit 0\n"
        )
        playwright_stub = dossier / "playwright-stub"
        playwright_stub.write_text(
            "#!/bin/sh\n"
            f'echo playwright $* >> "{self.journal}"\n'
            "exit 0\n"
        )
        uv_corps = (
            'echo uv $* >> "$JOURNAL"\n'
            "if [ \"$1\" = sync ]; then\n"
            "  mkdir -p .venv/bin\n"
            f"  cp '{python_stub}' .venv/bin/python\n"
            f"  cp '{playwright_stub}' .venv/bin/playwright\n"
            "  chmod +x .venv/bin/python .venv/bin/playwright\n"
            "fi\n"
            "exit 0"
        )
        uv_stub = dossier / "uv-stub"
        uv_stub.write_text(f"#!/bin/sh\nJOURNAL=\"{self.journal}\"\n{uv_corps}\n")
        uv_stub.chmod(0o755)
        self._commande("docker", "echo docker $* >> \"$JOURNAL\"; exit 0")
        self._commande(
            "curl",
            f'echo curl $* >> "{self.journal}"\n'
            f'cat <<EOF\nmkdir -p "$HOME/.local/bin"\ncp "{uv_stub}" "$HOME/.local/bin/uv"\nchmod +x "$HOME/.local/bin/uv"\nEOF\n',
        )
        if avec_uv:
            self._commande("uv", uv_corps)

    def ecrire_roles(self, racines: list[str]) -> None:
        chemins = "".join(f"      - {racine}\n" for racine in racines)
        (self.depot / "agents").mkdir(exist_ok=True)
        (self.depot / "agents" / "roles.yml").write_text(
            "roles:\n  test-roots:\n    paths:\n" + chemins
        )

    def lancer(self, *, extra_env: dict[str, str] | None = None) -> Resultat:
        chemin = f"{self.bin}{os.pathsep}{os.environ['PATH']}"
        if not self.avec_uv:
            chemin = f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"
        env = os.environ | {
            "PATH": chemin,
            "HOME": str(self.home),
            "JOURNAL": str(self.journal),
            "PYTEST_CODE": "0",
        }
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            ["bash", str(self.depot / "scripts" / "lancer-les-tests.sh")],
            cwd=self.depot,
            capture_output=True,
            text=True,
            env=env,
            timeout=DELAI_S,
        )
        return Resultat(
            proc.returncode,
            proc.stdout + proc.stderr,
            self._lire_env(),
            self.journal.read_text().splitlines() if self.journal.exists() else [],
        )

    def _racine(self, rel: str, *, playwright: bool = False) -> None:
        dossier = self.depot / rel
        dossier.mkdir(parents=True)
        deps = 'dev = ["pytest>=8", "pytest-playwright>=0.7"]' if playwright else 'dev = ["pytest>=8"]'
        (dossier / "pyproject.toml").write_text(
            "[project]\nname = \"x\"\nversion = \"0\"\n"
            "[dependency-groups]\n"
            f"{deps}\n"
        )

    def _commande(self, nom: str, corps: str) -> None:
        chemin = self.bin / nom
        chemin.write_text(f"#!/bin/sh\nJOURNAL=\"{self.journal}\"\n{corps}\n")
        chemin.chmod(0o755)

    def _lire_env(self) -> dict[str, str]:
        fichier = self.depot / ".env"
        if not fichier.is_file():
            return {}
        valeurs = {}
        for ligne in fichier.read_text().splitlines():
            if "=" in ligne and not ligne.startswith("#"):
                cle, valeur = ligne.split("=", 1)
                valeurs[cle] = valeur
        return valeurs


@pytest.fixture
def depot(tmp_path: Path) -> Depot:
    return Depot(tmp_path)


def test_le_script_prepare_un_env_avec_le_compte_administrateur_dexemple(depot):
    resultat = depot.lancer()

    assert resultat.code == 0, resultat.sortie
    assert resultat.env["ARGOS_IDENTIFIANT"] == COMPTE
    assert resultat.env["ARGOS_MOT_DE_PASSE"] == PHRASE
    assert resultat.env["ARGOS_VERSION"] == "0.7.0"


def test_le_script_lance_la_stack_avec_simulation_et_build(depot):
    resultat = depot.lancer()

    assert resultat.code == 0, resultat.sortie
    assert any(
        "compose" in ligne
        and "-f compose.yaml" in ligne
        and "-f compose.simulation.yaml" in ligne
        and "up -d --build --wait" in ligne
        for ligne in resultat.journal
    )


def test_le_script_lance_pytest_sur_chaque_racine_lue_dans_roles_yml(depot):
    resultat = depot.lancer()

    assert resultat.code == 0, resultat.sortie
    assert any(ligne.startswith("uv sync") for ligne in resultat.journal)
    assert any("python -m pytest" in ligne for ligne in resultat.journal)
    pytest_cwd = [ligne for ligne in resultat.journal if "python -m pytest" in ligne]
    assert len(pytest_cwd) >= 2


def test_le_script_s_arrete_a_la_premiere_racine_rouge(depot):
    resultat = depot.lancer(extra_env={"FAIL_RACINE": "tests/alpha"})

    assert resultat.code != 0
    pytest_cwd = [ligne for ligne in resultat.journal if "python -m pytest" in ligne]
    assert len(pytest_cwd) == 1
    assert "tests/alpha" in pytest_cwd[0]


def test_le_script_installe_chromium_playwright_pour_les_tests_web(depot):
    depot._racine("tests/web", playwright=True)
    depot.ecrire_roles(["tests/web/"])
    resultat = depot.lancer()

    assert resultat.code == 0, resultat.sortie
    assert any("playwright install" in ligne and "chromium" in ligne for ligne in resultat.journal)


def test_le_script_installe_uv_s_il_manque(tmp_path):
    depot = Depot(tmp_path, avec_uv=False)
    resultat = depot.lancer()

    assert resultat.code == 0, resultat.sortie
    assert any("curl" in ligne and "astral.sh/uv" in ligne for ligne in resultat.journal)
    assert any(ligne.startswith("uv sync") for ligne in resultat.journal)


WORKFLOW = REPO_ROOT / ".github" / "workflows" / "argos-tests.yml"


def test_le_workflow_appelle_le_script_sur_chaque_pr_vers_main():
    texte = WORKFLOW.read_text()

    assert "name: ArgOS tests" in texte
    assert "pull_request" in texte
    assert "main" in texte
    assert "ubuntu-latest" in texte
    assert "cancel-in-progress: true" in texte
    assert "scripts/lancer-les-tests.sh" in texte
    assert "actions/checkout@" in texte
    assert "SONAR" not in texte
    assert "cache" not in texte.lower()
    assert "secrets." not in texte
