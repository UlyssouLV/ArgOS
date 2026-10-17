"""README : deux hébergements (local, Ubuntu) et une section Développer distincte."""

from conftest import REPO_ROOT

README = (REPO_ROOT / "README.md").read_text()


def section(titre: str) -> str:
    marque = f"## {titre}"
    debut = README.index(marque)
    suite = README.find("\n## ", debut + len(marque))
    return README[debut:] if suite == -1 else README[debut:suite]


def test_hebergement_local_et_ubuntu_ont_prerequis_configuration_et_lancement():
    for titre in ("Hébergement local", "Hébergement Ubuntu"):
        texte = section(titre)
        assert "### Prérequis" in texte
        assert "### Configuration" in texte
        assert "### Installation / lancement" in texte


def test_hebergement_local_lance_le_site_avec_les_cameras_simulees():
    texte = section("Hébergement local")
    assert "lancer-argos.command" in texte
    assert "Caméras simulées" in texte
    assert "compose.simulation.yaml" in texte


def test_hebergement_ubuntu_documente_save_load_le_script_opt_argos_et_systemd():
    texte = section("Hébergement Ubuntu")
    assert "docker save" in texte
    assert "docker load" in texte
    assert "installer-le-site.sh" in texte
    assert "/opt/argos" in texte
    assert "argos.service" in texte
    assert "linux/amd64" in texte
    assert "DOCKER_DEFAULT_PLATFORM" in texte


def test_developper_est_distinct_de_lhebergement_local():
    local = section("Hébergement local")
    developper = section("Développer")
    assert "/t" in developper
    assert "uv" in developper
    assert "Node" in developper
    assert "/t" not in local
    assert "## Développer" in README
    assert README.index("## Hébergement local") < README.index("## Développer")


def test_developper_exige_le_check_argos_tests_sur_main():
    developper = section("Développer")
    assert "ArgOS tests / ArgOS tests" in developper
    assert "main" in developper
    assert "Settings" in developper
    assert "checks requis" in developper or "check requis" in developper
    assert "CI" in developper


def test_readme_ne_dit_pas_serveur_pour_le_site():
    assert "Serveur" not in README
    assert "serveur" not in README
