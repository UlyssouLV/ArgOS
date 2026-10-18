"""Volume Compose et config d’enregistrement du pont (issue #116, ADR 0011)."""

from pathlib import Path

from conftest import REPO_ROOT
from test_compose_autonome import config_prod

CIBLE = "/enregistrements"


def _montage_enregistrements(tmp_path: Path) -> dict:
    montages = config_prod(tmp_path, "compose.yaml")["services"]["mediamtx"].get("volumes") or []
    for montage in montages:
        if montage.get("target") == CIBLE:
            return montage
    raise AssertionError(f"aucun montage {CIBLE} sur mediamtx : {montages}")


def test_compose_declare_le_volume_enregistrements_et_le_monte_en_ecriture_sur_le_pont(tmp_path):
    config = config_prod(tmp_path, "compose.yaml")

    assert "enregistrements" in config["volumes"]
    montage = _montage_enregistrements(tmp_path)
    assert montage["type"] == "volume"
    assert montage["source"] == "enregistrements"
    assert not montage.get("read_only")


def test_la_config_du_pont_fixe_fmp4_une_minute_une_heure_et_le_chemin_par_camera():
    texte = (REPO_ROOT / "media" / "mediamtx.yml").read_text()

    assert "pathDefaults:" in texte
    assert "recordFormat: fmp4" in texte
    assert "recordSegmentDuration: 1m" in texte
    assert "recordDeleteAfter: 1h" in texte
    assert "recordPath: /enregistrements/%path/" in texte
    assert "record: no" in texte or "record: false" in texte


def test_la_doc_explique_comment_inspecter_le_volume_sur_un_site():
    readme = (REPO_ROOT / "README.md").read_text()
    page = (REPO_ROOT / "docs" / "cameras" / "inspecter-les-enregistrements.md").read_text()

    assert "inspecter-les-enregistrements.md" in readme
    assert "docker volume" in page
    assert "enregistrements" in page
    assert "camera-" in page
    assert "/opt/argos" in page
