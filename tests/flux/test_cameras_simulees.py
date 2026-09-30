"""Les Flux des Caméras simulées, vus de l'extérieur : RTSP conforme et playlist HLS."""

import json
import subprocess
import urllib.request

import pytest

from conftest import CAMERAS_SIMULEES, HOTE, PORT_HLS, PORT_RTSP

IMAGE_FFPROBE = "linuxserver/ffmpeg:version-7.1-cli"
# Le conteneur ffprobe joint l'hôte via ses ports publiés, comme un client du réseau local.
HOTE_DEPUIS_CONTENEUR = "host.docker.internal"


def ffprobe(camera: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "--add-host", f"{HOTE_DEPUIS_CONTENEUR}:host-gateway",
            "--entrypoint", "ffprobe",
            IMAGE_FFPROBE,
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-select_streams", "v:0",
            "-count_frames",
            "-read_intervals", "%+#60",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames",
            "-of", "json",
            f"rtsp://{HOTE_DEPUIS_CONTENEUR}:{PORT_RTSP}/{camera}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("camera", CAMERAS_SIMULEES)
def test_diffuse_du_h264_1280x720_decodable(camera):
    resultat = ffprobe(camera)

    assert resultat.returncode == 0, resultat.stderr
    (flux,) = json.loads(resultat.stdout)["streams"]
    assert flux["codec_name"] == "h264"
    assert (flux["width"], flux["height"]) == (1280, 720)
    assert int(flux["nb_read_frames"]) >= 1


@pytest.mark.parametrize("camera", CAMERAS_SIMULEES)
def test_a_une_playlist_hls(camera):
    url = f"http://{HOTE}:{PORT_HLS}/{camera}/index.m3u8"

    with urllib.request.urlopen(url, timeout=10) as reponse:
        assert reponse.status == 200
        assert reponse.read().decode().startswith("#EXTM3U")


def test_cam404_est_refusee_en_rtsp():
    resultat = ffprobe("cam404")

    assert resultat.returncode != 0
    assert "404" in resultat.stderr, resultat.stderr
