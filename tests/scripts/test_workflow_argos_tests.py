"""Contrat du workflow GitHub Actions qui appelle le script CI."""

from conftest import REPO_ROOT

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
    assert "ArgOS tests / ArgOS tests" not in texte


def test_le_workflow_compartimente_les_suites_avec_build_puis_pull():
    texte = WORKFLOW.read_text()

    assert "workflow_dispatch" in texte
    assert "fail-fast: false" in texte
    assert "fromJson(needs.plan.outputs.roots)" in texte
    assert "name: ArgOS tests" in texte
    assert "lire_test_roots.py" in texte
    assert "scripts/publier-images-ci.sh" in texte
    assert "--depuis-registre" in texte
    assert "needs: [plan, build]" in texte
    assert "needs: [plan, build, suite]" in texte
    assert "if: always()" in texte
    assert "packages: write" in texte
    assert "github.token" in texte
    assert "ci-${GITHUB_SHA}" in texte or "ci-${{ github.sha }}" in texte or 'tag=ci-${GITHUB_SHA}' in texte
    assert "tests/api/" in texte
    assert "tests/web/" in texte
