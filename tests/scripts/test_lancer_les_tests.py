"""Script CI (`/t -a`) : `.env` d’exemple, stack avec simulation, pytest par racine `test-roots`."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "lancer-les-tests.sh"
LIRE_RACINES = REPO_ROOT / "scripts" / "lire_test_roots.py"
DELAI_S = 15


def _affectation_bash(nom: str) -> str:
    for ligne in SCRIPT.read_text().splitlines():
        if ligne.startswith(f"{nom}="):
            return ligne.split("=", 1)[1].strip().strip('"')
    raise AssertionError(f"{nom} introuvable dans {SCRIPT}")


COMPTE = _affectation_bash("COMPTE")
PHRASE = _affectation_bash("PHRASE")


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
        shutil.copy2(LIRE_RACINES, self.depot / "scripts" / "lire_test_roots.py")
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

    def lancer(
        self,
        *racines: str,
        extra_env: dict[str, str] | None = None,
    ) -> Resultat:
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
        cmd = ["bash", str(self.depot / "scripts" / "lancer-les-tests.sh"), *racines]
        proc = subprocess.run(
            cmd,
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
    assert any(ligne.startswith("uv sync --no-build") for ligne in resultat.journal)
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
    assert any(
        "curl" in ligne
        and "astral.sh/uv" in ligne
        and "--proto" in ligne
        and "=https" in ligne
        for ligne in resultat.journal
    )
    assert any(ligne.startswith("uv sync --no-build") for ligne in resultat.journal)


def test_le_script_ne_lance_que_les_racines_passees_en_argument(depot):
    resultat = depot.lancer("tests/beta/")

    assert resultat.code == 0, resultat.sortie
    pytest_cwd = [ligne for ligne in resultat.journal if "python -m pytest" in ligne]
    assert len(pytest_cwd) == 1
    assert "tests/beta" in pytest_cwd[0]


def test_le_script_refuse_une_racine_absente_de_test_roots(depot):
    resultat = depot.lancer("tests/inconnue/")

    assert resultat.code != 0
    assert "inconnue" in resultat.sortie
    assert not any("python -m pytest" in ligne for ligne in resultat.journal)
