"""Contrat du workflow qui publie les images :staging (early access /ps) sur ghcr."""

from conftest import REPO_ROOT

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-staging.yml"
SCRIPT = REPO_ROOT / "scripts" / "publier-images-staging.sh"


def test_le_workflow_publie_staging_multi_arch_sur_dispatch():
    yaml = WORKFLOW.read_text()
    script = SCRIPT.read_text()

    assert "name: Publier images staging" in yaml
    assert "workflow_dispatch:" in yaml
    assert "push:" not in yaml
    assert "pull_request" not in yaml
    assert "release:" not in yaml
    assert "scripts/lancer-les-tests.sh" not in yaml
    assert "packages: write" in yaml
    assert "secrets.GITHUB_TOKEN" in yaml
    assert "docker/setup-qemu-action@" in yaml
    assert "docker/setup-buildx-action@" in yaml
    assert "docker/login-action@" in yaml
    assert "scripts/publier-images-staging.sh" in yaml
    assert "SONAR" not in yaml
    assert "public" in yaml.lower()

    assert "linux/amd64,linux/arm64" in script
    assert "--push" in script
    assert ":latest" not in script
    assert "publier ghcr.io/ulyssoulv/argos-api:staging api" in script
    assert "publier ghcr.io/ulyssoulv/argos-web:staging web" in script
    assert "publier ghcr.io/ulyssoulv/argos-pont:staging media" in script
    assert "publier ghcr.io/ulyssoulv/argos-certificats:staging certificats" in script
    assert "publier ghcr.io/ulyssoulv/argos-temps:staging temps" in script
    assert "argos-temps" in yaml
