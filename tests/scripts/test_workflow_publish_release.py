"""Contrat : une GitHub Release vX.Y.Z promeut :staging (même digest) et joint l'artefact du Site."""

import os
import subprocess
import tarfile
from pathlib import Path

from conftest import REPO_ROOT

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-release.yml"
SCRIPT_PROMOUVOIR = REPO_ROOT / "scripts" / "promouvoir-images-release.sh"
SCRIPT_ARTEFACT = REPO_ROOT / "scripts" / "assembler-artefact-site.sh"
DELAI_S = 10


def test_le_workflow_promouvoit_staging_vers_la_release_sans_rebuild():
    yaml = WORKFLOW.read_text()
    script = SCRIPT_PROMOUVOIR.read_text()

    assert "release:" in yaml
    assert "published" in yaml
    assert "push:" not in yaml
    assert "pull_request" not in yaml
    assert "packages: write" in yaml
    assert "contents: write" in yaml
    assert "secrets.GITHUB_TOKEN" in yaml
    assert "docker/login-action@" in yaml
    assert "scripts/promouvoir-images-release.sh" in yaml
    assert "scripts/assembler-artefact-site.sh" in yaml
    assert "gh release upload" in yaml
    assert "scripts/lancer-les-tests.sh" not in yaml
    assert "docker/setup-qemu-action@" not in yaml
    assert "SONAR" not in yaml

    assert "buildx imagetools create" in script
    assert "buildx build" not in script
    assert "--push" not in script
    assert ":staging" in script
    assert ":latest" in script
    assert "ghcr.io/ulyssoulv/argos-" in script
    for service in ("api", "web", "pont", "certificats", "temps"):
        assert service in script


def test_promouvoir_retaggue_le_digest_staging_vers_la_version_et_latest(tmp_path: Path):
    journal = tmp_path / "docker.txt"
    binaire = tmp_path / "bin"
    binaire.mkdir()
    (binaire / "docker").write_text(f'#!/bin/sh\necho "$*" >> "{journal}"\n')
    (binaire / "docker").chmod(0o755)

    proc = subprocess.run(
        ["bash", str(SCRIPT_PROMOUVOIR)],
        capture_output=True,
        text=True,
        env=os.environ | {
            "PATH": f"{binaire}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_REF_NAME": "v0.7.3",
        },
        timeout=DELAI_S,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    commandes = journal.read_text()
    assert "buildx build" not in commandes
    for service in ("api", "web", "pont", "certificats", "temps"):
        assert f"--tag ghcr.io/ulyssoulv/argos-{service}:0.7.3" in commandes
        assert f"--tag ghcr.io/ulyssoulv/argos-{service}:latest" in commandes
        assert f"ghcr.io/ulyssoulv/argos-{service}:staging" in commandes


def test_l_artefact_du_site_a_compose_et_detection_sans_env_ni_secrets(tmp_path: Path):
    archive = tmp_path / "argos-site.tar.gz"
    proc = subprocess.run(
        ["bash", str(SCRIPT_ARTEFACT), str(archive)],
        capture_output=True,
        text=True,
        timeout=DELAI_S,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert archive.is_file()

    with tarfile.open(archive) as tar:
        noms = tar.getnames()
        extraits = {membre.name: tar.extractfile(membre).read() for membre in tar.getmembers() if membre.isfile()}

    assert any(n.endswith("compose.yaml") for n in noms)
    assert any(n.endswith("compose.reseau-cameras.yaml") for n in noms)
    assert any(n.endswith("scripts/cameras/configurer-detection.sh") for n in noms)
    assert any(n.endswith("scripts/mettre-a-jour-le-site.sh") for n in noms)
    assert any(n.endswith("scripts/lib-fichiers-site.sh") for n in noms)
    assert any(n.endswith("argos.service") for n in noms)
    assert not any(n.rstrip("/").endswith(".env") or "/.env" in n for n in noms)
    assert not any(Path(n).name.startswith("._") for n in noms)
    assert not any("SONAR" in n for n in noms)
    textes = "\n".join(
        brut.decode()
        for nom, brut in extraits.items()
        if nom.endswith((".yaml", ".sh", ".service"))
    )
    assert "SONAR_" not in textes
    assert extraits[[n for n in extraits if n.endswith("compose.yaml")][0]] == (
        REPO_ROOT / "compose.yaml"
    ).read_bytes()
