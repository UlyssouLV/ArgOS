"""Note agents : protéger main avec le nom exact du check GitHub."""

from conftest import REPO_ROOT

NOTE = REPO_ROOT / "agents" / "docs" / "checks-requis-sur-main.md"


def test_la_note_reprend_le_nom_exact_du_check_et_les_ci_futures():
    assert NOTE.is_file()
    texte = NOTE.read_text()
    assert "**`ArgOS tests`**" in texte
    assert "ArgOS tests / ArgOS tests" not in texte
    assert "main" in texte
    assert "Settings" in texte
    assert "CI" in texte
    assert "API" in texte
