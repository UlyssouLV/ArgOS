"""Script de configuration de la Détection : prises retenues dans `.env`, sous-réseaux recalculés à chaque lancement."""

import pytest

from conftest import QUESTION, ifconfig_macos, ip_linux

INTERFACES = "ARGOS_DETECTION_CAMERAS_INTERFACES"
SOUS_RESEAUX = "ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX"


@pytest.mark.parametrize(
    ("systeme", "sortie_reseau", "prise"),
    [
        ("Linux", ip_linux(("lo", "127.0.0.1/8"), ("eth0", "192.168.1.23/24")), "eth0"),
        (
            "Darwin",
            ifconfig_macos(("lo0", "127.0.0.1", "0xff000000"), ("en0", "192.168.1.23", "0xffffff00")),
            "en0",
        ),
    ],
    ids=["linux", "macos"],
)
def test_une_seule_prise_pas_de_question_sous_reseau_ecrit(machine, systeme, sortie_reseau, prise):
    machine.systeme(systeme, sortie_reseau)

    resultat = machine.lancer(terminal=True)

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert resultat.env[INTERFACES] == prise
    assert resultat.env[SOUS_RESEAUX] == "192.168.1.0/24"
    assert resultat.env["ARGOS_IDENTIFIANT"] == "administrateur"


def test_prise_retenue_sous_reseau_recalcule_quand_son_adresse_change(machine):
    machine.ecrire_env(f"{INTERFACES}=eth1\n{SOUS_RESEAUX}=192.168.1.0/24\n")
    machine.systeme("Linux", ip_linux(("eth0", "10.0.0.5/24"), ("eth1", "192.168.50.7/24")))

    resultat = machine.lancer(terminal=True)

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert resultat.env[INTERFACES] == "eth1"
    assert resultat.env[SOUS_RESEAUX] == "192.168.50.0/24"


def test_docker_boucle_locale_et_169_254_ecartes(machine):
    machine.systeme(
        "Linux",
        ip_linux(
            ("lo", "127.0.0.1/8"),
            ("docker0", "172.17.0.1/16"),
            ("br-3f2a9c", "172.18.0.1/16"),
            ("veth5d1e", "172.19.0.1/24"),
            ("eth0", "169.254.12.4/16"),
            ("eth1", "192.168.1.23/24"),
        ),
    )

    resultat = machine.lancer(terminal=True)

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert resultat.env[INTERFACES] == "eth1"
    assert resultat.env[SOUS_RESEAUX] == "192.168.1.0/24"


def test_plusieurs_prises_en_terminal_question_et_choix_retenus(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24"), ("eth1", "10.10.0.2/24"), ("eth2", "10.20.0.2/24")))

    resultat = machine.lancer(terminal=True, reponses="1 3\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION in resultat.sortie
    assert "eth1" in resultat.sortie and "10.10.0.0/24" in resultat.sortie
    assert resultat.env[INTERFACES] == "eth0,eth2"
    assert resultat.env[SOUS_RESEAUX] == "192.168.1.0/24,10.20.0.0/24"


def test_prise_sans_adresse_reglage_vide_et_avertissement(machine):
    machine.ecrire_env(f"{INTERFACES}=eth1\n{SOUS_RESEAUX}=192.168.50.0/24\n")
    machine.systeme("Linux", ip_linux(("eth0", "10.0.0.5/24")))

    resultat = machine.lancer(terminal=True)

    assert resultat.code == 0, resultat.sortie
    assert "eth1" in resultat.sortie and "pas d'adresse" in resultat.sortie
    assert resultat.env[INTERFACES] == "eth1"
    assert resultat.env[SOUS_RESEAUX] == ""


@pytest.mark.parametrize(
    "prises",
    [
        [("eth0", "10.0.0.5/16")],
        [("eth0", "10.0.0.5/22"), ("eth1", "192.168.1.2/24")],
    ],
    ids=["une-prise", "total-de-deux-prises"],
)
def test_plage_de_plus_de_1024_adresses_refusee_et_expliquee(machine, prises):
    machine.ecrire_env(f"{INTERFACES}={','.join(nom for nom, _ in prises)}\n{SOUS_RESEAUX}=192.168.1.0/24\n")
    machine.systeme("Linux", ip_linux(*prises))

    resultat = machine.lancer(terminal=True)

    assert resultat.code != 0
    assert "1024" in resultat.sortie
    assert resultat.env[SOUS_RESEAUX] == ""


def test_1024_adresses_acceptees(machine):
    machine.ecrire_env(f"{INTERFACES}=eth0,eth1\n")
    machine.systeme("Linux", ip_linux(("eth0", "10.0.0.5/23"), ("eth1", "192.168.0.2/23")))

    resultat = machine.lancer(terminal=True)

    assert resultat.code == 0, resultat.sortie
    assert resultat.env[SOUS_RESEAUX] == "10.0.0.0/23,192.168.0.0/23"


def test_sans_terminal_aucune_question_garde_la_prise_retenue(machine):
    machine.ecrire_env(f"{INTERFACES}=eth1\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24"), ("eth1", "10.10.0.2/24")))

    resultat = machine.lancer(terminal=False)

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert resultat.env[INTERFACES] == "eth1"
    assert resultat.env[SOUS_RESEAUX] == "10.10.0.0/24"


def test_sans_terminal_ni_prise_retenue_aucune_question_reglage_vide(machine):
    machine.ecrire_env(f"{SOUS_RESEAUX}=192.168.1.0/24\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24"), ("eth1", "10.10.0.2/24")))

    resultat = machine.lancer(terminal=False)

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie
    assert "terminal" in resultat.sortie
    assert INTERFACES not in resultat.env
    assert resultat.env[SOUS_RESEAUX] == ""
