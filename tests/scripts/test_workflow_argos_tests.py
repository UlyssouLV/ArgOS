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
