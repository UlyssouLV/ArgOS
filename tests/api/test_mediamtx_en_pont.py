"""MediaMTX en pont (docs/adr/0001-mediamtx-en-pont.md), vu de l'extérieur de la stack.

Toute Caméra active est relayée sur `rtsp://<hôte>:8554/<chemin_flux>` après un tour de
réconciliation (10 s). Les Caméras simulées s'y déclarent sur leur chemin de vraie caméra :
c'est le conteneur `mediamtx`, rattaché à leur réseau, qui tire le Flux.
"""

import json
import subprocess
import time

from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_etat_cameras import url_simulee

IMAGE_FFPROBE = "linuxserver/ffmpeg:version-7.1-cli"
# Le conteneur ffprobe joint l'hôte via ses ports publiés, comme un client du réseau local.
HOTE_DEPUIS_CONTENEUR = "host.docker.internal"
PORT_RTSP = 8554
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
