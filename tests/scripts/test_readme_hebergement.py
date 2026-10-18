"""README : hébergements (local, Ubuntu), staging machine perso, Développer distinct."""

from conftest import REPO_ROOT

README = (REPO_ROOT / "README.md").read_text()
RESEAU = (REPO_ROOT / "docs" / "cameras" / "reseau-et-detection.md").read_text()
SECURITE = (REPO_ROOT / "docs" / "securite.md").read_text()


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


def test_hebergement_ubuntu_documente_pull_la_maj_et_le_secours_save_load():
    texte = section("Hébergement Ubuntu")
    assert "docker pull" in texte or "compose pull" in texte
    assert "installer-le-site.sh" in texte
    assert "/opt/argos" in texte
    assert "argos.service" in texte
    assert "mettre-a-jour-le-site.sh" in texte
    assert "docker save" in texte
    assert "docker load" in texte
    assert "secours" in texte.lower() or "hors ligne" in texte.lower() or "hors-ligne" in texte.lower()
    assert "Danger Zone" in texte
    assert "Public" in texte


def test_hebergement_ubuntu_branche_la_maj_au_boot_et_en_commande():
    texte = section("Hébergement Ubuntu")
    assert "boot" in texte.lower() or "démarrage" in texte.lower() or "restart" in texte.lower()
    assert "sudo" in texte
    assert "/opt/argos/scripts/mettre-a-jour-le-site.sh" in texte


def test_essayer_staging_sur_machine_perso_macos_et_windows():
    texte = section("Essayer staging")
    assert "ARGOS_VERSION=staging" in texte
    assert "Docker Desktop" in texte
    assert "macOS" in texte
    assert "Windows" in texte
    assert "compose.yaml" in texte
    assert "docker compose -f compose.yaml pull" in texte
    assert "installer-le-site.sh" not in texte


def test_doc_isolement_vlan_deux_prises_sans_internet_hote_tire_ghcr():
    assert "deux prises" in RESEAU.lower() or "Deux prises" in RESEAU
    assert "sans" in RESEAU and "internet" in RESEAU.lower()
    assert "ghcr" in RESEAU.lower()
    assert "macvlan" in RESEAU
    assert "VLAN" in SECURITE or "vlan" in SECURITE.lower()
    assert "reseau-et-detection.md" in SECURITE or "Réseau et Détection" in SECURITE


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
    assert "**`ArgOS tests`**" in developper
    assert "ArgOS tests / ArgOS tests" not in developper
    assert "main" in developper
    assert "Settings" in developper
    assert "checks requis" in developper or "check requis" in developper
    assert "CI" in developper


def test_readme_ne_dit_pas_serveur_pour_le_site():
    assert "Serveur" not in README
    assert "serveur" not in README
