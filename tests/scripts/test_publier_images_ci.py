"""Contrat du script qui pousse les images ci-<sha> pour la matrix de tests."""

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "publier-images-ci.sh"
SIMULATION = REPO_ROOT / "compose.simulation.yaml"


def test_le_script_pousse_site_et_simulation_sous_argos_version():
    texte = SCRIPT.read_text()

    assert "ARGOS_VERSION" in texte
    assert "docker build" in texte
    assert "docker push" in texte
    assert "argos-api" in texte
    assert "argos-web" in texte
    assert "argos-pont" in texte
    assert "argos-certificats" in texte
    assert "argos-temps" in texte
    assert "argos-camera-simulee" in texte
    assert "argos-onvif-simule" in texte
    assert "linux/amd64,linux/arm64" not in texte
    assert '--build-arg "ARGOS_VERSION=$TAG"' in texte


def test_la_simulation_porte_image_et_build_comme_le_site():
    texte = SIMULATION.read_text()

    assert "ghcr.io/ulyssoulv/argos-camera-simulee:${ARGOS_VERSION" in texte
    assert "ghcr.io/ulyssoulv/argos-onvif-simule:${ARGOS_VERSION" in texte
    assert "build: ./media/simulated" in texte
    assert "build: ./simulation/onvif" in texte
