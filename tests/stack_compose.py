"""Outils communs aux racines de tests qui tournent contre la stack Docker Compose lancée.

Importé par les `conftest.py` de `tests/api/` et `tests/web/` (sans dépendance : stdlib, pytest, httpx).
"""

import functools
import os
import socket
import ssl
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# La stack des tests porte la simulation : Caméras simulées superposées à la stack de prod.
FICHIERS_COMPOSE = ("compose.yaml", "compose.simulation.yaml")
# L'origine unique du Site (docs/adr/0005-…) : UI, API (/api) et Live (/flux), en HTTPS.
URL_SITE = "https://localhost"
COOKIE_SESSION = "argos_session"
DELAI_PRET_S = 120
CLES_ADMINISTRATEUR = ("ARGOS_IDENTIFIANT", "ARGOS_MOT_DE_PASSE")
# Délai d'expiration d'un Aperçu sans renouvellement, raccourci pour les tests (2 minutes en prod).
EXPIRATION_APERCU_S = 30
# Identifiants de dev de camera-simulee-2 (media/simulated/README.md).
IDENTIFIANTS_SIMULES = {2: "admin:argos-simulee"}
# Chemins de vraies caméras des Caméras simulées (media/simulated/README.md).
CHEMINS_SIMULES = {
    1: "Streaming/Channels/101",
    2: "cam/realmonitor?channel=1&subtype=0",
    3: "flux",
    4: "Streaming/Channels/101",
}
# MAC et IP fixes des Caméras simulées (compose.simulation.yaml), MAC au format affiché par ArgOS.
MACS_SIMULEES = {n: f"02:a6:05:00:00:0{n}" for n in CHEMINS_SIMULES}
IPS_SIMULEES = {n: f"172.30.0.1{n}" for n in CHEMINS_SIMULES}
RESEAU_SIMULATION = "cameras-simulees"
# Interfaces ONVIF des Caméras simulées (simulation/onvif/README.md).
SIMULATEURS_ONVIF = ("camera-simulee-2-onvif", "camera-simulee-4-onvif")
# Lancé dans `api` : envoie une enveloppe SOAP à une adresse ONVIF ; faute SOAP → code de sortie non nul.
_ENVOYER_SOAP = """
import sys, urllib.request
adresse, corps = sys.argv[1:]
enveloppe = ('<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"'
             ' xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl"'
             ' xmlns:tt="http://www.onvif.org/ver10/schema"><env:Body>' + corps + '</env:Body></env:Envelope>')
requete = urllib.request.Request(adresse, data=enveloppe.encode(), headers={"Content-Type": "application/soap+xml"})
urllib.request.urlopen(requete, timeout=5).read()
"""


def compose(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """`env` : variables de plus, lues par l'interpolation des fichiers compose."""
    return _compose_avec_fichiers(FICHIERS_COMPOSE, *args, env=env)


def _lire_env() -> dict[str, str]:
    chemin = REPO_ROOT / ".env"
    if not chemin.exists():
        return {}
    valeurs = {}
    for ligne in chemin.read_text().splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            valeurs[cle.strip()] = valeur.strip().strip("\"'")
    return valeurs


@functools.cache
def autorite_du_site() -> str:
    """Partie publique de l'Autorité du Site (PEM), lue dans son volume par le service `certificats`."""
    return compose(
        "run", "--rm", "--no-deps", "-T", "--entrypoint", "cat", "certificats", "/autorite/autorite.crt"
    ).stdout


def contexte_tls() -> ssl.SSLContext:
    """Ne fait confiance qu'à l'Autorité du Site : le certificat présenté par le Site est toujours vérifié."""
    return ssl.create_default_context(cadata=autorite_du_site())


def certificat_presente(hote: str = "localhost") -> bytes:
    """Certificat serveur (DER) présenté par l'origine du Site, après vérification contre l'Autorité."""
    with socket.create_connection((hote, 443), timeout=5) as brut:
        with contexte_tls().wrap_socket(brut, server_hostname=hote) as tls:
            return tls.getpeercert(binary_form=True)


def client_du_site(timeout: float = 10) -> httpx.Client:
    """Client HTTP de l'origine du Site, comme un navigateur qui a installé l'Autorité."""
    return httpx.Client(base_url=URL_SITE, timeout=timeout, verify=contexte_tls())


def _repond(url: str) -> bool:
    try:
        return httpx.get(url, timeout=5, verify=contexte_tls()).status_code == 200
    except httpx.TransportError:
        return False


def attendre(url: str) -> None:
    echeance = time.monotonic() + DELAI_PRET_S
    while not _repond(url):
        if time.monotonic() > echeance:
            pytest.fail(f"{url} ne répond pas après {DELAI_PRET_S} s")
        time.sleep(1)


def attendre_api() -> None:
    attendre(f"{URL_SITE}/api/docs")


def redemarrer_api() -> None:
    compose("restart", "api")
    attendre_api()


def hotes_declares() -> list[str]:
    """IP (ou noms) du Site sur le réseau local, déclarées dans `.env` : nommées par le certificat serveur."""
    return [hote.strip() for hote in _lire_env().get("MTX_WEBRTCADDITIONALHOSTS", "").split(",") if hote.strip()]


def identifiants_administrateur() -> dict[str, str]:
    """Lus dans `.env` ; s'ils manquent, échec immédiat qui dit quoi ajouter."""
    env = _lire_env()
    manquantes = [cle for cle in CLES_ADMINISTRATEUR if not env.get(cle)]
    if manquantes:
        pytest.fail(
            "Identifiants de l'Administrateur absents de .env : ajouter "
            + ", ".join(f"{cle}=…" for cle in manquantes)
            + " (voir .env.example), puis relancer.",
            pytrace=False,
        )
    return {
        "identifiant": env["ARGOS_IDENTIFIANT"],
        "mot_de_passe": env["ARGOS_MOT_DE_PASSE"],
    }


def url_camera_simulee(numero: int, requete: str, identifiants: bool = True, chemin: str | None = None) -> str:
    """URL d'une Caméra simulée, vue de `api` et du pont ; `identifiants` ne joue que pour camera-simulee-2.

    `chemin` remplace son chemin de vraie caméra. La requête rend l'URL unique (l'URL est unique parmi
    les Caméras) ; la Caméra simulée l'ignore.
    """
    utilisateur = f"{IDENTIFIANTS_SIMULES[numero]}@" if identifiants and numero in IDENTIFIANTS_SIMULES else ""
    chemin = chemin or CHEMINS_SIMULES[numero]
    separateur = "&" if "?" in chemin else "?"
    return f"rtsp://{utilisateur}camera-simulee-{numero}/{chemin}{separateur}test={requete}"


def remettre_onvif_en_usine() -> None:
    """Recrée les simulateurs ONVIF : leur état, en mémoire, revient « sortie d'usine »."""
    compose("up", "-d", "--force-recreate", "--wait", *SIMULATEURS_ONVIF)


def camera_simulee_4_sans_recreation_de_la_date() -> None:
    """Recrée l'interface ONVIF de camera-simulee-4, « sortie d'usine », sans savoir recréer la date et l'heure.

    `remettre_onvif_en_usine` lui rend ensuite les deux types d'Incrustation.
    """
    compose(
        "up", "-d", "--force-recreate", "--wait", "camera-simulee-4-onvif", env={"ONVIF_TYPES_CREABLES_4": "Plain"}
    )


def camera_simulee_2_en_tls_ancien() -> None:
    """Recrée l'interface ONVIF de camera-simulee-2, « sortie d'usine », en TLS 1.0 au plus (même certificat).

    `remettre_onvif_en_usine` lui rend ensuite un TLS récent.
    """
    compose("up", "-d", "--force-recreate", "--wait", "camera-simulee-2-onvif", env={"ONVIF_TLS_MAX_2": "1.0"})


def camera_simulee_2_avec_une_autre_cle() -> None:
    """Recrée l'interface ONVIF de camera-simulee-2 avec un nouveau certificat, d'une autre clé, à la même adresse.

    Hors du volume : `remettre_onvif_en_usine` lui rend ensuite son certificat habituel.
    """
    compose(
        "up",
        "-d",
        "--force-recreate",
        "--wait",
        "camera-simulee-2-onvif",
        env={"ONVIF_CERTIFICAT_2": "/tmp/autre-certificat.pem", "ONVIF_CLE_2": "/tmp/autre-cle.pem"},
    )


def camera_simulee_2_sans_https() -> None:
    """Recrée l'interface ONVIF de camera-simulee-2 en HTTP seulement (8899) : HTTPS a disparu.

    `remettre_onvif_en_usine` lui rend ensuite HTTPS, avec le même certificat.
    """
    compose("up", "-d", "--force-recreate", "--wait", "camera-simulee-2-onvif", env={"ONVIF_PORT_HTTPS_2": ""})


def camera_simulee_2_sans_media_2() -> None:
    """Recrée l'interface ONVIF de camera-simulee-2, « sortie d'usine », sans média 2 : le repli média 1 en H.264.

    `remettre_onvif_en_usine` lui rend ensuite le média 2.
    """
    compose("up", "-d", "--force-recreate", "--wait", "camera-simulee-2-onvif", env={"ONVIF_SERVICES_2": "image"})


def camera_simulee_2_muette_apres_encodage(secondes: int) -> None:
    """Recrée l'interface ONVIF de camera-simulee-2, « sortie d'usine », muette `secondes` après un changement
    d'Encodage. `remettre_onvif_en_usine` lui rend ensuite une réponse immédiate.
    """
    compose(
        "up",
        "-d",
        "--force-recreate",
        "--wait",
        "camera-simulee-2-onvif",
        env={"ONVIF_SILENCE_APRES_ENCODAGE_S_2": str(secondes)},
    )


def couper_puis_rendre_le_flux_simule(numero: int) -> None:
    """Recrée camera-simulee-`numero` : son Flux se coupe le temps du redémarrage, puis revient à la même adresse."""
    compose("up", "-d", "--force-recreate", "--wait", f"camera-simulee-{numero}")


def requetes_onvif_recues(service: str, depuis: datetime, de: str, schema_port: str) -> list[str]:
    """Lignes du journal d'une interface ONVIF simulée : requêtes reçues depuis `depuis`, de l'IP `de`, sur
    `schema_port` (`https:443`, `http:8899`). Le healthcheck, local, n'y est pas compté.
    """
    journal = compose("logs", "--no-log-prefix", "--since", depuis.isoformat(), service).stdout
    return [ligne for ligne in journal.splitlines() if ligne.startswith(f"{de} {schema_port} ")]


def regler_camera_simulee_4_en_onvif(service: str, corps: str) -> None:
    """Envoie une requête SOAP (`corps` de l'enveloppe) à l'interface ONVIF de camera-simulee-4, sans identifiants.

    `service` : `device` ou `media`. Par le conteneur `api`, seul à joindre le réseau des Caméras simulées.
    """
    adresse = f"http://camera-simulee-4:80/onvif/{service}_service"
    compose("exec", "-T", "api", "python", "-c", _ENVOYER_SOAP, adresse, corps)


def adresses_ip(service: str) -> set[str]:
    """Adresses IPv4 du conteneur d'un service, sur tous ses réseaux Compose."""
    conteneur = compose("ps", "-q", service).stdout.strip()
    inspection = subprocess.run(
        ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", conteneur],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(inspection.stdout.split())


def deplacer_cameras_simulees(adresses: dict[int, str], macs: dict[int, str] | None = None) -> None:
    """Donne à chaque Caméra simulée (par numéro) sa nouvelle IP, MAC et nom Compose gardés : un nouveau bail DHCP.

    `macs` remplace la MAC de certaines : à la même IP, c'est alors un autre Appareil qui sert le même Flux.
    Recrée les services via un override Compose (pas `NetworkConnect`) : sur les runners CI, l'API Docker
    ignore `MacAddress` au rattachement, alors que `mac_address` à la création est respecté.
    """
    macs = MACS_SIMULEES | (macs or {})
    services = [f"camera-simulee-{numero}" for numero in adresses]
    onvif = [f"camera-simulee-{numero}-onvif" for numero in adresses if numero in (2, 4)]
    lignes = ["services:"]
    for numero, ip in adresses.items():
        lignes += [
            f"  camera-simulee-{numero}:",
            "    networks:",
            f"      {RESEAU_SIMULATION}:",
            f"        ipv4_address: {ip}",
            f'        mac_address: "{macs[numero]}"',
        ]
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as override:
        override.write("\n".join(lignes) + "\n")
        chemin_override = override.name
    try:
        # ONVIF d'abord : `network_mode: service:camera-simulee-N` ne survit pas à l'arrêt du parent.
        # Un seul `up` avec l'override encore présent : Compose attache ONVIF au parent recréé.
        a_arreter = (*onvif, *services)
        compose("stop", *a_arreter)
        _compose_avec_fichiers(
            (*FICHIERS_COMPOSE, chemin_override),
            "up",
            "-d",
            "--force-recreate",
            "--wait",
            *services,
            *onvif,
        )
    finally:
        Path(chemin_override).unlink(missing_ok=True)
    for numero, ip in adresses.items():
        attendu = {(ip, macs[numero])}
        vu = _adresses_et_macs(f"camera-simulee-{numero}")
        if vu != attendu:
            raise RuntimeError(f"camera-simulee-{numero}: IP/MAC {vu}, attendu {attendu}")


def remettre_cameras_simulees() -> None:
    """Remet à leur IP et MAC fixes les Caméras simulées déplacées ou changées d'Appareil."""
    deplacees = {
        n: ip
        for n, ip in IPS_SIMULEES.items()
        if _adresses_et_macs(f"camera-simulee-{n}") != {(ip, MACS_SIMULEES[n])}
    }
    if deplacees:
        deplacer_cameras_simulees(deplacees)


def _adresses_et_macs(service: str) -> set[tuple[str, str]]:
    conteneur = compose("ps", "-q", service).stdout.strip()
    inspection = subprocess.run(
        ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}/{{.MacAddress}} {{end}}", conteneur],
        capture_output=True,
        text=True,
        check=True,
    )
    return {tuple(adresse.split("/")) for adresse in inspection.stdout.split()}


def _compose_avec_fichiers(fichiers: tuple[str, ...], *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Comme `compose`, avec une liste explicite de fichiers (`-f`), absolus ou relatifs au dépôt."""
    try:
        return subprocess.run(
            ["docker", "compose", *(option for fichier in fichiers for option in ("-f", fichier)), *args],
            cwd=REPO_ROOT,
            env={**os.environ, "ARGOS_APERCU_EXPIRATION_S": str(EXPIRATION_APERCU_S), **(env or {})},
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as erreur:
        # pytest n'affiche pas stderr de CalledProcessError par défaut.
        for flux in (erreur.stderr, erreur.stdout):
            if flux and flux.strip():
                erreur.add_note(flux[-4000:])
        raise


def lancer_stack() -> None:
    # --build : les tests visent toujours le code courant, pas une image périmée.
    compose("up", "-d", "--build", "--wait")
    attendre_api()
