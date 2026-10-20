"""Service `temps`, Serveur de temps du Site (docs/adr/0014-serveur-de-temps-du-site.md).

L'image est lancée seule, comme dans la stack mais sur un réseau Docker de test : on l'interroge en NTP
(UDP 123 publié sur l'hôte), sur une source injoignable (repli sur l'horloge du serveur) puis sur un autre
`temps` pris pour source, donnée par l'environnement ou par le fichier de réglage qu'écrit `api`.
"""

import socket
import struct
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE = "argos-temps-test"
# Adresse de documentation (RFC 5737) : jamais joignable.
SOURCE_INJOIGNABLE = "192.0.2.1"
# Capacités du service dans compose.yaml : ni SYS_TIME, ni DAC_OVERRIDE.
CAPACITES = (
    "--cap-drop", "ALL",
    *(option for capacite in ("CHOWN", "NET_BIND_SERVICE", "SETGID", "SETUID") for option in ("--cap-add", capacite)),
)
# Secondes entre l'époque NTP (1900) et l'époque Unix (1970).
EPOQUE_NTP = 2_208_988_800
STRATE_DU_REPLI = 10
ECART_MAX_S = 1.0
DELAI_S = 60


@dataclass
class ReponseNtp:
    strate: int
    reference: bytes
    heure: float


def interroger(port: int) -> ReponseNtp:
    """Une requête NTP client (version 4, mode 3) vers 127.0.0.1:`port`."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as prise:
        prise.settimeout(2)
        prise.sendto(b"\x23" + bytes(47), ("127.0.0.1", port))
        paquet, _ = prise.recvfrom(512)
    secondes, fraction = struct.unpack("!II", paquet[40:48])
    return ReponseNtp(paquet[1], paquet[12:16], secondes - EPOQUE_NTP + fraction / 2**32)


def attendre_reponse(port: int, condition=lambda reponse: True) -> ReponseNtp:
    fin = time.monotonic() + DELAI_S
    derniere = None
    while time.monotonic() < fin:
        try:
            derniere = interroger(port)
        except OSError:
            derniere = None
        if derniere is not None and condition(derniere):
            return derniere
        time.sleep(1)
    raise AssertionError(f"temps n'a pas répondu comme attendu en {DELAI_S} s (dernière réponse : {derniere})")


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=DELAI_S)


@pytest.fixture(scope="session")
def image() -> str:
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(REPO_ROOT / "temps")], check=True, capture_output=True)
    return IMAGE


@pytest.fixture
def reseau() -> Iterator[str]:
    nom = f"argos-temps-test-{uuid.uuid4().hex[:8]}"
    docker("network", "create", nom)
    yield nom
    docker("network", "rm", nom, check=False)


@pytest.fixture
def lancer(image: str, reseau: str) -> Iterator:
    conteneurs: list[str] = []

    def _lancer(source: str, reglage: Path | None = None) -> tuple[str, int]:
        """Lance `temps` sur `source`, UDP 123 publié sur un port libre de 127.0.0.1 : (nom, port).

        `reglage` : dossier monté en lecture seule comme le volume que partage `api`."""
        nom = f"argos-temps-test-{uuid.uuid4().hex[:8]}"
        montage = ("-v", f"{reglage}:/reglage:ro") if reglage else ()
        docker(
            "run", "-d", "--name", nom, "--network", reseau,
            "-e", f"ARGOS_TEMPS_SOURCE={source}",
            *montage,
            *CAPACITES,
            "-p", "127.0.0.1::123/udp",
            image,
        )
        conteneurs.append(nom)
        port = int(docker("port", nom, "123/udp").stdout.split(":")[-1])
        return nom, port

    yield _lancer
    for nom in conteneurs:
        docker("rm", "-f", nom, check=False)


def adresse_ip(nom: str) -> str:
    return docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", nom).stdout.strip()


def test_source_injoignable_temps_sert_l_horloge_du_serveur(lancer):
    _, port = lancer(SOURCE_INJOIGNABLE)

    reponse = attendre_reponse(port)

    assert reponse.strate == STRATE_DU_REPLI
    assert abs(reponse.heure - time.time()) < ECART_MAX_S


def test_temps_suit_sa_source_et_sert_une_heure_proche_d_elle(lancer):
    source, port_source = lancer(SOURCE_INJOIGNABLE)
    attendre_reponse(port_source)
    _, port = lancer(source)

    reponse = attendre_reponse(port, lambda r: r.strate == STRATE_DU_REPLI + 1)

    # Identifiant de référence d'une source IPv4 : son adresse.
    assert socket.inet_ntoa(reponse.reference) == adresse_ip(source)
    heure_source = interroger(port_source).heure
    assert abs(reponse.heure - heure_source) < ECART_MAX_S
    # Il garde sa source, sans retomber sur l'horloge du serveur (strate 10).
    time.sleep(5)
    assert interroger(port).strate == STRATE_DU_REPLI + 1


def test_temps_suit_la_source_reglee_par_api_sans_redemarrer(lancer, tmp_path):
    source, port_source = lancer(SOURCE_INJOIGNABLE)
    attendre_reponse(port_source)
    reglage = tmp_path / "reglage"
    reglage.mkdir()
    # Ligne vide : l'horloge du serveur, même si l'environnement donne une source.
    (reglage / "source").write_text("\n")
    nom, port = lancer(source, reglage)
    assert attendre_reponse(port).strate == STRATE_DU_REPLI

    (reglage / "source").write_text(f"{adresse_ip(source)}\n")
    suivie = attendre_reponse(port, lambda r: r.strate == STRATE_DU_REPLI + 1)
    assert socket.inet_ntoa(suivie.reference) == adresse_ip(source)

    (reglage / "source").write_text("\n")
    # Sans source, chrony garderait sa dernière estimation : temps le relance sur l'horloge du serveur.
    attendre_reponse(port, lambda r: r.strate == STRATE_DU_REPLI)
    # Le réglage suit sans redémarrer le conteneur.
    assert docker("inspect", "-f", "{{.RestartCount}}", nom).stdout.strip() == "0"


def test_temps_n_accepte_aucune_commande_chrony_par_le_reseau(lancer, image, reseau):
    nom, port = lancer(SOURCE_INJOIGNABLE)
    attendre_reponse(port)

    # Depuis le même réseau Docker : port de commande fermé.
    distant = docker(
        "run", "--rm", "--network", reseau, "--entrypoint", "chronyc", image,
        "-h", adresse_ip(nom), "tracking",
        check=False,
    )
    # Dans le conteneur, par sa socket locale : chrony répond.
    local = docker("exec", "-u", "chrony", nom, "chronyc", "-n", "tracking", check=False)

    assert distant.returncode != 0, distant.stdout
    assert local.returncode == 0, local.stdout + local.stderr


def test_temps_redemarre_et_repond_encore(lancer):
    nom, port = lancer(SOURCE_INJOIGNABLE)
    attendre_reponse(port)

    docker("restart", nom)
    port = int(docker("port", nom, "123/udp").stdout.split(":")[-1])

    assert attendre_reponse(port).strate == STRATE_DU_REPLI


def test_temps_ne_regle_pas_l_horloge_de_l_hote_et_se_dit_en_bonne_sante(lancer):
    nom, port = lancer(SOURCE_INJOIGNABLE)
    attendre_reponse(port)
    fin = time.monotonic() + DELAI_S
    while docker("inspect", "-f", "{{.State.Health.Status}}", nom).stdout.strip() != "healthy":
        assert time.monotonic() < fin, docker("inspect", "-f", "{{json .State.Health}}", nom).stdout
        time.sleep(1)

    capacites = docker("inspect", "-f", "{{.HostConfig.CapAdd}}", nom).stdout
    # Dernière colonne de `docker top` : la commande de chaque processus.
    (chronyd,) = [ligne.split() for ligne in docker("top", nom).stdout.splitlines() if "chronyd -" in ligne]

    assert "SYS_TIME" not in capacites
    assert "-x" in chronyd
