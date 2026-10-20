"""Réseau des caméras (macvlan, prod Linux) : IP d'ArgOS proposée, retenue dans `.env`, et fichier Compose activé.

Sous macOS, rien ne change : Docker Desktop ne gère pas macvlan (ADR 0003).
"""

import json
import os
import subprocess

import pytest

from conftest import QUESTION, QUESTION_IP, QUESTION_IP_TEMPS, REPO_ROOT, ifconfig_macos, ip_linux

INTERFACES = "ARGOS_DETECTION_CAMERAS_INTERFACES"
IP = "ARGOS_RESEAU_CAMERAS_IP"
PRISE = "ARGOS_RESEAU_CAMERAS_PRISE"
SOUS_RESEAU = "ARGOS_RESEAU_CAMERAS_SOUS_RESEAU"
IP_TEMPS = "ARGOS_RESEAU_CAMERAS_TEMPS_IP"
FICHIER = "compose.reseau-cameras.yaml"


def fichiers_compose(env: dict[str, str]) -> list[str]:
    return [f for f in env.get("COMPOSE_FILE", "").split(":") if f]


def test_ip_libre_proposee_depuis_le_haut_du_sous_reseau_et_retenue(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=True, reponses="\n\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION_IP in resultat.sortie and "192.168.1.254" in resultat.sortie
    assert resultat.env[IP] == "192.168.1.254"
    assert resultat.env[PRISE] == "eth0"
    assert resultat.env[SOUS_RESEAU] == "192.168.1.0/24"
    assert fichiers_compose(resultat.env) == ["compose.yaml", FICHIER]


def test_ip_qui_repond_en_arp_ou_de_la_machine_jamais_proposee(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.252/24")))
    machine.voisins("192.168.1.254", "192.168.1.253")

    resultat = machine.lancer(terminal=True, reponses="\n\n")

    assert resultat.code == 0, resultat.sortie
    assert resultat.env[IP] == "192.168.1.251"


def test_ip_proposee_remplacable(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=True, reponses="192.168.1.200\n\n")

    assert resultat.code == 0, resultat.sortie
    assert resultat.env[IP] == "192.168.1.200"
    assert FICHIER in fichiers_compose(resultat.env)


@pytest.mark.parametrize("reponse", ["pas-une-ip", "10.0.0.5", "192.168.1.0", "192.168.1.255"])
def test_ip_saisie_invalide_ou_hors_du_sous_reseau_redemandee(machine, reponse):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=True, reponses=f"{reponse}\n192.168.1.200\n\n")

    assert resultat.code == 0, resultat.sortie
    assert resultat.sortie.count(QUESTION_IP) == 2
    assert resultat.env[IP] == "192.168.1.200"


def test_ip_retenue_gardee_sans_question_en_terminal_ou_non(machine):
    machine.ecrire_env(f"{IP}=192.168.1.200\n{IP_TEMPS}=192.168.1.201\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    for terminal in (True, False):
        resultat = machine.lancer(terminal=terminal)

        assert resultat.code == 0, resultat.sortie
        assert QUESTION_IP not in resultat.sortie
        assert resultat.env[IP] == "192.168.1.200"
        assert fichiers_compose(resultat.env) == ["compose.yaml", FICHIER]


def test_sans_terminal_ni_ip_retenue_reseau_des_cameras_non_active(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=False)

    assert resultat.code == 0, resultat.sortie
    assert QUESTION_IP not in resultat.sortie
    assert "terminal" in resultat.sortie
    assert IP not in resultat.env
    assert FICHIER not in fichiers_compose(resultat.env)
    # La Détection reste configurée, sans MAC pour les vraies caméras.
    assert resultat.env["ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX"] == "192.168.1.0/24"


def test_ip_retenue_hors_du_sous_reseau_avertissement_et_reseau_desactive(machine):
    machine.ecrire_env(f"{IP}=192.168.1.200\nCOMPOSE_FILE=compose.yaml:{FICHIER}\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.50.7/24")))

    resultat = machine.lancer(terminal=False)

    assert resultat.code == 0, resultat.sortie
    assert "[AVERTISSEMENT]" in resultat.sortie and "192.168.1.200" in resultat.sortie
    assert "192.168.50.0/24" in resultat.sortie
    assert resultat.env[IP] == "192.168.1.200"
    assert fichiers_compose(resultat.env) == ["compose.yaml"]


def test_ip_retenue_hors_du_sous_reseau_en_terminal_nouvelle_proposition(machine):
    machine.ecrire_env(f"{IP}=192.168.1.200\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.50.7/24")))

    resultat = machine.lancer(terminal=True, reponses="\n\n")

    assert resultat.code == 0, resultat.sortie
    assert "[AVERTISSEMENT]" in resultat.sortie
    assert resultat.env[IP] == "192.168.50.254"
    assert FICHIER in fichiers_compose(resultat.env)


def test_ip_retenue_qui_repond_en_arp_avertissement_et_reseau_desactive(machine):
    machine.ecrire_env(f"{IP}=192.168.1.200\nCOMPOSE_FILE=compose.yaml:{FICHIER}\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))
    machine.voisins("192.168.1.200")

    resultat = machine.lancer(terminal=False)

    assert resultat.code == 0, resultat.sortie
    assert "[AVERTISSEMENT]" in resultat.sortie and "répond déjà" in resultat.sortie
    assert resultat.env[IP] == "192.168.1.200"
    assert fichiers_compose(resultat.env) == ["compose.yaml"]


def test_compose_file_existant_complete_une_seule_fois(machine):
    machine.ecrire_env(f"{IP}=192.168.1.200\n{IP_TEMPS}=192.168.1.201\nCOMPOSE_FILE=compose.yaml:compose.override.yaml\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    machine.lancer(terminal=False)
    resultat = machine.lancer(terminal=False)

    assert fichiers_compose(resultat.env) == ["compose.yaml", "compose.override.yaml", FICHIER]


def test_plusieurs_prises_macvlan_sur_la_premiere_seulement(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24"), ("eth1", "10.10.0.2/24")))

    resultat = machine.lancer(terminal=True, reponses="1 2\n\n\n")

    assert resultat.code == 0, resultat.sortie
    assert resultat.sortie.count(QUESTION_IP) == 1
    assert resultat.env[PRISE] == "eth0"
    assert resultat.env[IP] == "192.168.1.254"
    assert "eth1" in resultat.sortie and "sans MAC" in resultat.sortie


def test_macos_aucun_changement_jamais_compose_file(machine):
    machine.ecrire_env("ARGOS_IDENTIFIANT=administrateur\n")
    machine.systeme("Darwin", ifconfig_macos(("en0", "192.168.1.23", "0xffffff00")))

    resultat = machine.lancer(terminal=True, reponses="\n\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION not in resultat.sortie and QUESTION_IP not in resultat.sortie
    assert set(resultat.env) == {"ARGOS_IDENTIFIANT", INTERFACES, "ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX"}


def test_seconde_ip_libre_proposee_pour_temps_juste_sous_celle_d_argos(machine):
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=True, reponses="\n\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION_IP_TEMPS in resultat.sortie and "192.168.1.253" in resultat.sortie
    assert resultat.env[IP] == "192.168.1.254"
    assert resultat.env[IP_TEMPS] == "192.168.1.253"
    assert fichiers_compose(resultat.env) == ["compose.yaml", FICHIER]


def test_ip_de_temps_qui_repond_en_arp_ou_d_argos_jamais_proposee(machine):
    machine.ecrire_env(f"{IP}=192.168.1.254\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))
    machine.voisins("192.168.1.253")

    resultat = machine.lancer(terminal=True, reponses="\n")

    assert resultat.code == 0, resultat.sortie
    assert QUESTION_IP not in resultat.sortie
    assert resultat.env[IP_TEMPS] == "192.168.1.252"


@pytest.mark.parametrize("reponse", ["192.168.1.254", "10.0.0.5", "pas-une-ip"])
def test_ip_de_temps_egale_a_celle_d_argos_ou_invalide_redemandee(machine, reponse):
    machine.ecrire_env(f"{IP}=192.168.1.254\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=True, reponses=f"{reponse}\n192.168.1.201\n")

    assert resultat.code == 0, resultat.sortie
    assert resultat.sortie.count(QUESTION_IP_TEMPS) == 2
    assert resultat.env[IP_TEMPS] == "192.168.1.201"


def test_ip_de_temps_retenue_gardee_sans_question(machine):
    machine.ecrire_env(f"{IP}=192.168.1.200\n{IP_TEMPS}=192.168.1.201\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    for terminal in (True, False):
        resultat = machine.lancer(terminal=terminal)

        assert resultat.code == 0, resultat.sortie
        assert QUESTION_IP_TEMPS not in resultat.sortie
        assert resultat.env[IP_TEMPS] == "192.168.1.201"
        assert fichiers_compose(resultat.env) == ["compose.yaml", FICHIER]
        assert "192.168.1.201" in resultat.sortie


def test_sans_terminal_ni_ip_de_temps_retenue_reseau_des_cameras_non_active(machine):
    # Site d'avant la 0.9.0 : IP d'ArgOS seule.
    machine.ecrire_env(f"{IP}=192.168.1.200\nCOMPOSE_FILE=compose.yaml:{FICHIER}\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))

    resultat = machine.lancer(terminal=False)

    assert resultat.code == 0, resultat.sortie
    assert "[AVERTISSEMENT]" in resultat.sortie and "terminal" in resultat.sortie
    assert IP_TEMPS not in resultat.env
    assert fichiers_compose(resultat.env) == ["compose.yaml"]


def test_ip_de_temps_retenue_qui_repond_en_arp_ou_egale_a_celle_d_argos_reseau_desactive(machine):
    for temps, voisins in (("192.168.1.201", ("192.168.1.201",)), ("192.168.1.200", ())):
        machine.ecrire_env(f"{IP}=192.168.1.200\n{IP_TEMPS}={temps}\nCOMPOSE_FILE=compose.yaml:{FICHIER}\n")
        machine.systeme("Linux", ip_linux(("eth0", "192.168.1.23/24")))
        machine.voisins(*voisins)

        resultat = machine.lancer(terminal=False)

        assert resultat.code == 0, resultat.sortie
        assert "[AVERTISSEMENT]" in resultat.sortie and temps in resultat.sortie
        assert fichiers_compose(resultat.env) == ["compose.yaml"]


def test_ip_de_temps_retenue_hors_du_sous_reseau_en_terminal_nouvelle_proposition(machine):
    machine.ecrire_env(f"{IP}=192.168.50.200\n{IP_TEMPS}=192.168.1.201\n")
    machine.systeme("Linux", ip_linux(("eth0", "192.168.50.7/24")))

    resultat = machine.lancer(terminal=True, reponses="\n")

    assert resultat.code == 0, resultat.sortie
    assert "[AVERTISSEMENT]" in resultat.sortie and "192.168.1.201" in resultat.sortie
    assert resultat.env[IP_TEMPS] == "192.168.50.254"
    assert FICHIER in fichiers_compose(resultat.env)


def config_compose(dossier, *fichiers: str, env: str) -> dict:
    fichier_env = dossier / "exemple.env"
    fichier_env.write_text(env)
    environnement = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "ARGOS_"))}
    proc = subprocess.run(
        [
            "docker", "compose", "--env-file", str(fichier_env),
            *(option for fichier in fichiers for option in ("-f", fichier)),
            "config", "--format", "json",
        ],
        cwd=REPO_ROOT,
        env=environnement,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


EXEMPLE_ENV = f"{PRISE}=eth0\n{SOUS_RESEAU}=192.168.1.0/24\n{IP}=192.168.1.254\n{IP_TEMPS}=192.168.1.253\n"


def test_compose_reseau_des_cameras_valide_avec_un_env_d_exemple(tmp_path):
    config = config_compose(tmp_path, "compose.yaml", FICHIER, env=EXEMPLE_ENV)

    reseau = next(r for nom, r in config["networks"].items() if nom == "reseau-cameras")
    assert reseau["driver"] == "macvlan"
    assert reseau["driver_opts"] == {"parent": "eth0"}
    assert reseau["ipam"]["config"] == [{"subnet": "192.168.1.0/24"}]
    api = config["services"]["api"]
    assert api["networks"]["reseau-cameras"]["ipv4_address"] == "192.168.1.254"
    assert api["environment"]["ARGOS_RESEAU_CAMERAS_ADRESSES"] == "192.168.1.254"
    temps = config["services"]["temps"]
    assert temps["networks"]["reseau-cameras"]["ipv4_address"] == "192.168.1.253"
    # Joint à son IP du réseau des caméras : plus rien de publié sur l'hôte.
    assert not temps.get("ports")
    # api et temps seuls rejoignent le réseau des caméras.
    autres = {nom: s.get("networks", {}) for nom, s in config["services"].items() if nom not in ("api", "temps")}
    assert all("reseau-cameras" not in reseaux for reseaux in autres.values())


def test_compose_yaml_seul_sans_macvlan(tmp_path):
    config = config_compose(tmp_path, "compose.yaml", env=EXEMPLE_ENV)

    assert all(r.get("driver") != "macvlan" for r in config.get("networks", {}).values())
    assert "ARGOS_RESEAU_CAMERAS_ADRESSES" not in config["services"]["api"]["environment"]
