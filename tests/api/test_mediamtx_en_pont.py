"""MediaMTX en pont (docs/adr/0001-mediamtx-en-pont.md), vu de l'extérieur de la stack.

Toute Caméra active est relayée sur `rtsp://mediamtx:8554/<chemin_flux>` après un tour de
réconciliation (10 s), et en LL-HLS fMP4 sous l'origine HTTPS du Site, `/flux/hls/<chemin_flux>/`, pour le H.265
(docs/adr/0004-hls-pour-les-flux-h265.md, docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md). Les Caméras simulées s'y déclarent sur leur chemin de vraie caméra :
c'est le conteneur `mediamtx`, rattaché à leur réseau, qui tire le Flux.

RTSP n'est servi qu'au réseau Compose (docs/adr/0006-flux-authentifies-par-nginx.md) : fermé à l'hôte vu du réseau
local, republié par la simulation sur `127.0.0.1:8554` pour la machine du développeur.
"""

import functools
import json
import re
import socket
import subprocess
import time

import httpx
import pytest

from stack_compose import client_du_site, compose
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_connexion import se_connecter
from test_etat_cameras import url_simulee

IMAGE_FFPROBE = "linuxserver/ffmpeg:version-7.1-cli"
# Le conteneur ffprobe, rattaché au réseau de la stack, y joint le pont par son nom Compose.
PONT = "mediamtx"
PORT_RTSP = 8554
CHEMIN_HLS = "/flux/hls"
# Un tour de réconciliation (10 s) + démarrage du Flux à la demande, avec de la marge.
DELAI_RELAIS_S = 45


@functools.cache
def reseau_de_la_stack() -> str:
    """Nom Docker du réseau par défaut de la stack (préfixé par le projet Compose)."""
    return json.loads(compose("config", "--format", "json").stdout)["networks"]["default"]["name"]


def hote_vu_du_reseau_local() -> str:
    """L'hôte du Site tel qu'un poste du réseau local le joint : par une interface autre que son loopback.

    La passerelle du réseau de la stack, et non `host.docker.internal` : sous Docker Desktop, celui-ci mène au
    loopback du Mac, où la simulation republie justement `8554`.
    """
    return subprocess.run(
        ["docker", "network", "inspect", "-f", "{{range .IPAM.Config}}{{.Gateway}}{{end}}", reseau_de_la_stack()],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def lisible(chemin: str, hote: str = PONT) -> bool:
    """Vrai si ffprobe, dans un conteneur du réseau de la stack, lit au moins une image H.264 sur `hote`."""
    resultat = subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", reseau_de_la_stack(),
            "--entrypoint", "ffprobe",
            IMAGE_FFPROBE,
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-select_streams", "v:0",
            "-count_frames",
            "-read_intervals", "%+#5",
            "-show_entries", "stream=codec_name,nb_read_frames",
            "-of", "json",
            f"rtsp://{hote}:{PORT_RTSP}/{chemin}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if resultat.returncode != 0:
        return False
    flux = json.loads(resultat.stdout).get("streams", [])
    return any(f["codec_name"] == "h264" and int(f.get("nb_read_frames", 0)) >= 1 for f in flux)


def decrit_depuis_la_machine_hote(chemin: str) -> str:
    """Réponse RTSP à un `DESCRIBE` de `chemin`, envoyé depuis la machine hôte sur `127.0.0.1:8554`."""
    with socket.create_connection(("127.0.0.1", PORT_RTSP), timeout=10) as connexion:
        connexion.sendall(
            f"DESCRIBE rtsp://127.0.0.1:{PORT_RTSP}/{chemin} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n".encode()
        )
        with connexion.makefile("rb") as lue:
            entetes = b"".join(iter(lue.readline, b"\r\n"))
            longueur = re.search(rb"(?im)^content-length:\s*(\d+)", entetes)
            corps = lue.read(int(longueur.group(1))) if longueur else b""
    return (entetes + b"\r\n" + corps).decode()


def ffprobe_http(lecteur: httpx.Client, url: str) -> dict:
    """Premier flux vidéo lu par ffprobe dans un fichier servi par le pont (codec et tag du conteneur).

    Le fichier est lu par l'origine HTTPS (certificat vérifié), puis passé à ffprobe sur son entrée.
    """
    contenu = lecteur.get(url).raise_for_status().content
    resultat = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "--entrypoint", "ffprobe",
            IMAGE_FFPROBE,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,codec_tag_string",
            "-of", "json",
            "pipe:0",
        ],
        input=contenu,
        capture_output=True,
        timeout=60,
    )
    assert resultat.returncode == 0, resultat.stderr.decode()
    (flux,) = json.loads(resultat.stdout)["streams"]
    return flux


def attendre_playlist(lecteur: httpx.Client, url: str) -> str:
    """Playlist servie par le pont, une fois le chemin réconcilié et le muxer HLS prêt.

    `lecteur` garde les cookies, comme un navigateur : MediaMTX y retient la session HLS.
    """
    echeance = time.monotonic() + DELAI_RELAIS_S
    while True:
        reponse = lecteur.get(url, follow_redirects=True)  # MediaMTX vérifie d'abord les cookies (302)
        if reponse.status_code == 200:
            return reponse.text
        assert time.monotonic() < echeance, f"{url} : {reponse.status_code}"
        time.sleep(1)


def attendre_lisible(chemin: str, attendu: bool) -> None:
    echeance = time.monotonic() + DELAI_RELAIS_S
    while lisible(chemin) != attendu:
        assert time.monotonic() < echeance, f"{chemin} {'toujours illisible' if attendu else 'encore lisible'}"
        time.sleep(1)


def test_chemin_flux_d_une_camera_active_puis_null_apres_desactivation(connecte, creer_camera):
    camera = creer_camera().json()

    desactivee = connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False}).json()
    reactivee = connecte.patch(f"/api/cameras/{camera['id']}", json={"active": True}).json()

    assert camera["chemin_flux"] == f"camera-{camera['id']}"
    assert desactivee["chemin_flux"] is None
    assert reactivee["chemin_flux"] == camera["chemin_flux"]


def test_camera_simulee_relayee_en_h264(creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()

    attendre_lisible(camera["chemin_flux"], True)


def test_camera_simulee_a_identifiants_relayee_en_h264(creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(2)).json()

    attendre_lisible(camera["chemin_flux"], True)


def test_camera_desactivee_plus_relayee(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()
    attendre_lisible(camera["chemin_flux"], True)

    connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False})

    attendre_lisible(camera["chemin_flux"], False)


def test_le_relais_suit_le_changement_d_url(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1, "inconnu")).json()
    # Chemin réconcilié, mais sa source n'existe pas.
    time.sleep(12)
    assert not lisible(camera["chemin_flux"])

    connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": url_simulee(2)})

    attendre_lisible(camera["chemin_flux"], True)


def test_rtsp_du_pont_ferme_a_l_hote_vu_du_reseau_local(creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()
    attendre_lisible(camera["chemin_flux"], True)

    assert not lisible(camera["chemin_flux"], hote_vu_du_reseau_local())


def test_rtsp_du_pont_lisible_depuis_la_machine_hote_avec_la_simulation(creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()
    attendre_lisible(camera["chemin_flux"], True)

    reponse = decrit_depuis_la_machine_hote(camera["chemin_flux"])

    assert reponse.startswith("RTSP/1.0 200"), reponse
    assert "m=video" in reponse, reponse


@pytest.fixture
def lecteur(administrateur):
    """Lecteur HLS sous l'origine HTTPS du Site, connecté comme l'Administrateur : les Flux exigent une session (ADR 0006)."""
    with client_du_site() as c:
        assert se_connecter(c, **administrateur).status_code == 204
        yield c


def test_camera_h265_servie_en_ll_hls_fmp4_hvc1_sans_reencodage(creer_camera, lecteur):
    camera = creer_camera(url_rtsp=url_simulee(4)).json()
    url_maitresse = f"{CHEMIN_HLS}/{camera['chemin_flux']}/index.m3u8"

    maitresse = attendre_playlist(lecteur, url_maitresse)
    assert re.search(r'CODECS="hvc1\.', maitresse), maitresse

    (variante,) = [ligne for ligne in maitresse.splitlines() if ligne and not ligne.startswith("#")]
    url_variante = httpx.URL(url_maitresse).join(variante)
    playlist = attendre_playlist(lecteur, str(url_variante))
    # Low-latency : des parties de segment ; fMP4 : un segment d'initialisation.
    assert "#EXT-X-PART:" in playlist, playlist
    (init,) = re.findall(r'#EXT-X-MAP:URI="([^"]+)"', playlist)

    assert ffprobe_http(lecteur, str(url_variante.join(init))) == {"codec_name": "hevc", "codec_tag_string": "hvc1"}
