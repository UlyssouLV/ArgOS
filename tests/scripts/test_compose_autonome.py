"""Compose de prod autonome : images du dépôt étiquetées, sans simulation."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from conftest import REPO_ROOT

IMAGES_DU_SITE = {
    "api": "argos-api",
    "web": "argos-web",
    "mediamtx": "argos-pont",
    "certificats": "argos-certificats",
}
VERSION = "9.9.9"


def config_prod(dossier: Path, *fichiers: str, env: str = f"ARGOS_VERSION={VERSION}\n") -> dict:
    fichier_env = dossier / "exemple.env"
    fichier_env.write_text(env)
    environnement = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "ARGOS_"))}
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(fichier_env),
            *(option for fichier in fichiers for option in ("-f", fichier)),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        env=environnement,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_le_repli_compose_sans_env_est_la_version_de_production_courante():
    compose = (REPO_ROOT / "compose.yaml").read_text()
    assert compose.count("${ARGOS_VERSION:-0.7.2}") == 4
    assert "ARGOS_VERSION:-0.7.0" not in compose


def test_les_quatre_images_du_site_portent_le_registre_et_argos_version(tmp_path):
    config = config_prod(tmp_path, "compose.yaml")

    for service, nom in IMAGES_DU_SITE.items():
        assert config["services"][service]["image"] == f"ghcr.io/ulyssoulv/{nom}:{VERSION}"
        assert "build" in config["services"][service]


def test_le_pont_n_a_plus_besoin_du_fichier_mediamtx_du_depot(tmp_path):
    volumes = config_prod(tmp_path, "compose.yaml")["services"]["mediamtx"].get("volumes", [])
    sources = [str(volume.get("source", "")) + str(volume.get("target", "")) for volume in volumes]

    assert not any("mediamtx.yml" in source for source in sources)


def test_compose_prod_valide_avec_argos_version_sans_les_sources_ni_simulation(tmp_path):
    shutil.copy(REPO_ROOT / "compose.yaml", tmp_path / "compose.yaml")
    (tmp_path / ".env").write_text(f"ARGOS_VERSION={VERSION}\n")
    environnement = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "ARGOS_"))}
    proc = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "config", "--format", "json"],
        cwd=tmp_path,
        env=environnement,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    config = json.loads(proc.stdout)
    assert not [s for s in config["services"] if s.startswith("camera-simulee")]
    assert config["services"]["api"]["image"] == f"ghcr.io/ulyssoulv/argos-api:{VERSION}"


def test_postgres_reste_epinglé_et_le_service_du_pont_s_appelle_mediamtx(tmp_path):
    config = config_prod(tmp_path, "compose.yaml")

    assert "mediamtx" in config["services"]
    assert "postgres:18.6-alpine3.24" in config["services"]["db"]["image"]
    assert "build" not in config["services"]["db"]


def test_la_simulation_et_le_lanceur_construisent_toujours_depuis_le_clone(tmp_path):
    config = config_prod(tmp_path, "compose.yaml", "compose.simulation.yaml")
    lanceur = (REPO_ROOT / "lancer-argos.command").read_text()

    assert "camera-simulee-1" in config["services"]
    assert "build" in config["services"]["api"]
    assert "compose.simulation.yaml" in lanceur
    assert "docker compose up -d --build --wait" in lanceur
