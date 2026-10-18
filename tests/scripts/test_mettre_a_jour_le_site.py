"""Mise à jour Ubuntu : Releases et filesystem factices, codes de sortie distincts."""

import json
import os
import subprocess
import tarfile
from pathlib import Path

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "mettre-a-jour-le-site.sh"
DELAI_S = 15
CODE_APPLIQUEE = 0
CODE_ECHEC = 1
CODE_RIEN = 2


def _ecrire_executable(chemin: Path, corps: str) -> None:
    chemin.write_text(f"#!/bin/sh\n{corps}\n")
    chemin.chmod(0o755)


def _artefact(dossier: Path, compose: str = "COMPOSE_NOUVEAU\n") -> Path:
    racine = dossier / "argos-site"
    (racine / "scripts" / "cameras").mkdir(parents=True)
    (racine / "compose.yaml").write_text(compose)
    (racine / "compose.reseau-cameras.yaml").write_text("RESEAU_NOUVEAU\n")
    (racine / "scripts" / "cameras" / "configurer-detection.sh").write_text("#!/bin/sh\n")
    (racine / "scripts" / "lib-fichiers-site.sh").write_text("# bundle Site\n")
    (racine / "scripts" / "mettre-a-jour-le-site.sh").write_text("#!/bin/sh\n")
    (racine / "argos.service").write_text("[Unit]\nDescription=ArgOS\n")
    archive = dossier / "argos-site.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(racine, arcname="argos-site")
    return archive


class Site:
    """Site Ubuntu simulé : /opt/argos, curl GitHub, docker."""

    def __init__(self, dossier: Path) -> None:
        self.prefixe = dossier / "prefixe"
        self.racine = self.prefixe / "opt" / "argos"
        self.racine.mkdir(parents=True)
        (self.racine / "scripts" / "cameras").mkdir(parents=True)
        (self.racine / "certificats").mkdir()
        (self.racine / "compose.yaml").write_text("COMPOSE_ANCIEN\n")
        (self.racine / "compose.reseau-cameras.yaml").write_text("RESEAU_ANCIEN\n")
        (self.racine / ".env").write_text(
            "ARGOS_VERSION=0.7.2\nARGOS_IDENTIFIANT=garder\nARGOS_MOT_DE_PASSE=secret\n"
        )
        (self.racine / "certificats" / "fourni.crt").write_text("CERTIFICAT_FOURNI\n")
        self.bin = dossier / "bin"
        self.bin.mkdir()
        self.journal_docker = dossier / "docker.txt"
        self.journal_curl = dossier / "curl.txt"
        self.releases = dossier / "releases.json"
        self.archive = _artefact(dossier)
        self.releases.write_text(
            json.dumps(
                [
                    {
                        "tag_name": "v0.7.2",
                        "prerelease": False,
                        "assets": [
                            {
                                "name": "argos-site.tar.gz",
                                "browser_download_url": "https://example.test/ancien.tar.gz",
                            }
                        ],
                    },
                    {
                        "tag_name": "v0.7.3",
                        "prerelease": False,
                        "assets": [
                            {
                                "name": "argos-site.tar.gz",
                                "browser_download_url": "https://example.test/argos-site.tar.gz",
                            }
                        ],
                    },
                ]
            )
        )
        _ecrire_executable(
            self.bin / "docker",
            f'echo "$*" >> "{self.journal_docker}"',
        )
        archive = self.archive
        releases = self.releases
        journal_curl = self.journal_curl
        _ecrire_executable(
            self.bin / "curl",
            f"""
echo "$*" >> "{journal_curl}"
out=""
url=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
  url="$a"
done
case "$url" in
  *releases*) cat "{releases}" ;;
  *argos-site.tar.gz*)
    if [ -n "$out" ]; then cp "{archive}" "$out"; else cat "{archive}"; fi
    ;;
  *) echo "url inconnue: $url" >&2; exit 1 ;;
esac
""",
        )

    def lancer(
        self,
        docker_corps: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if docker_corps is not None:
            _ecrire_executable(
                self.bin / "docker",
                docker_corps,
            )
        return subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=os.environ
            | {
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "ARGOS_PREFIX": str(self.prefixe),
            }
            | (extra_env or {}),
            timeout=DELAI_S,
        )

    def env(self) -> str:
        return (self.racine / ".env").read_text()


def test_rien_a_faire_si_deja_la_derniere_release_semver(tmp_path: Path):
    site = Site(tmp_path)
    (site.racine / ".env").write_text("ARGOS_VERSION=0.7.3\nARGOS_IDENTIFIANT=garder\n")

    proc = site.lancer()

    assert proc.returncode == CODE_RIEN, proc.stdout + proc.stderr
    assert not site.journal_docker.exists()
    assert (site.racine / "compose.yaml").read_text() == "COMPOSE_ANCIEN\n"
    assert "ARGOS_VERSION=0.7.3" in site.env()


def test_applique_l_artefact_sans_ecraser_env_ni_certificats_et_tire_les_images(tmp_path: Path):
    site = Site(tmp_path)

    proc = site.lancer()

    assert proc.returncode == CODE_APPLIQUEE, proc.stdout + proc.stderr
    assert (site.racine / "compose.yaml").read_text() == "COMPOSE_NOUVEAU\n"
    assert (site.racine / "compose.reseau-cameras.yaml").read_text() == "RESEAU_NOUVEAU\n"
    assert (site.racine / "scripts" / "mettre-a-jour-le-site.sh").is_file()
    assert (site.racine / "scripts" / "lib-fichiers-site.sh").is_file()
    env = site.env()
    assert "ARGOS_VERSION=0.7.3" in env
    assert "ARGOS_IDENTIFIANT=garder" in env
    assert "ARGOS_MOT_DE_PASSE=secret" in env
    assert (site.racine / "certificats" / "fourni.crt").read_text() == "CERTIFICAT_FOURNI\n"
    commandes = site.journal_docker.read_text()
    assert "compose pull" in commandes
    assert "force-recreate" in commandes


def test_echec_journalise_sans_rollback_automatique(tmp_path: Path):
    site = Site(tmp_path)
    journal = site.journal_docker

    proc = site.lancer(docker_corps=f'echo "$*" >> "{journal}"; exit 1')

    assert proc.returncode == CODE_ECHEC, proc.stdout + proc.stderr
    assert "[ERREUR]" in (proc.stdout + proc.stderr)
    env = site.env()
    assert "ARGOS_VERSION=0.7.3" in env
    assert "ARGOS_IDENTIFIANT=garder" in env
    assert (site.racine / "certificats" / "fourni.crt").read_text() == "CERTIFICAT_FOURNI\n"


def test_interroge_le_depot_github_indique(tmp_path: Path):
    site = Site(tmp_path)

    proc = site.lancer(extra_env={"ARGOS_GITHUB_DEPOT": "exemple/Depot"})

    assert proc.returncode == CODE_APPLIQUEE, proc.stdout + proc.stderr
    assert "repos/exemple/Depot/releases" in site.journal_curl.read_text()


def test_canal_staging_ne_suit_pas_les_releases_semver(tmp_path: Path):
    site = Site(tmp_path)
    (site.racine / ".env").write_text("ARGOS_VERSION=staging\n")

    proc = site.lancer()

    assert proc.returncode == CODE_RIEN, proc.stdout + proc.stderr
    assert (site.racine / "compose.yaml").read_text() == "COMPOSE_ANCIEN\n"


def test_choisit_la_plus_haute_semver_pas_l_ordre_lexicographique(tmp_path: Path):
    site = Site(tmp_path)
    site.releases.write_text(
        json.dumps(
            [
                {
                    "tag_name": "v0.7.3",
                    "prerelease": False,
                    "assets": [
                        {
                            "name": "argos-site.tar.gz",
                            "browser_download_url": "https://example.test/argos-site.tar.gz",
                        }
                    ],
                },
                {
                    "tag_name": "v0.7.10",
                    "prerelease": False,
                    "assets": [
                        {
                            "name": "argos-site.tar.gz",
                            "browser_download_url": "https://example.test/argos-site.tar.gz",
                        }
                    ],
                },
            ]
        )
    )

    proc = site.lancer()

    assert proc.returncode == CODE_APPLIQUEE, proc.stdout + proc.stderr
    assert "ARGOS_VERSION=0.7.10" in site.env()
