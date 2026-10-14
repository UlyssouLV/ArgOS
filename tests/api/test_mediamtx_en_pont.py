"""MediaMTX en pont (docs/adr/0001-mediamtx-en-pont.md), vu de l'extérieur de la stack.

Toute Caméra active est relayée sur `rtsp://<hôte>:8554/<chemin_flux>` après un tour de
réconciliation (10 s), et en LL-HLS fMP4 sous l'origine HTTPS du Site, `/flux/hls/<chemin_flux>/`, pour le H.265
(docs/adr/0004-hls-pour-les-flux-h265.md, docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md). Les Caméras simulées s'y déclarent sur leur chemin de vraie caméra :
c'est le conteneur `mediamtx`, rattaché à leur réseau, qui tire le Flux.
"""

import json
import re
import subprocess
import time

import httpx
import pytest

from stack_compose import client_du_site
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_etat_cameras import url_simulee

IMAGE_FFPROBE = "linuxserver/ffmpeg:version-7.1-cli"
# Le conteneur ffprobe joint l'hôte via ses ports publiés, comme un client du réseau local.
HOTE_DEPUIS_CONTENEUR = "host.docker.internal"
PORT_RTSP = 8554
CHEMIN_HLS = "/flux/hls"
# Un tour de réconciliation (10 s) + démarrage du Flux à la demande, avec de la marge.
DELAI_RELAIS_S = 45


def lisible(chemin: str) -> bool:
    """Vrai si ffprobe lit au moins une image H.264 sur le relais."""
    resultat = subprocess.run(
        [
            "docker", "run", "--rm",
            "--add-host", f"{HOTE_DEPUIS_CONTENEUR}:host-gateway",
            "--entrypoint", "ffprobe",
            IMAGE_FFPROBE,
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-select_streams", "v:0",
            "-count_frames",
            "-read_intervals", "%+#5",
            "-show_entries", "stream=codec_name,nb_read_frames",
            "-of", "json",
            f"rtsp://{HOTE_DEPUIS_CONTENEUR}:{PORT_RTSP}/{chemin}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if resultat.returncode != 0:
        return False
    flux = json.loads(resultat.stdout).get("streams", [])
    return any(f["codec_name"] == "h264" and int(f.get("nb_read_frames", 0)) >= 1 for f in flux)


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


@pytest.fixture
def lecteur():
    """Lecteur HLS sous l'origine HTTPS du Site, sans session ArgOS."""
    with client_du_site() as c:
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
