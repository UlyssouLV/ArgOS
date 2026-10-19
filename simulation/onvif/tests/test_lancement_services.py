"""Services, profils et fichier de la date incrustée choisis au lancement (`ONVIF_SERVICES`, `ONVIF_CHEMINS_RTSP`,
`ONVIF_FICHIER_DATE`), comme en conteneur."""

import time
from datetime import UTC, datetime, timedelta

from conftest import NS, NS_IMAGE, NS_MEDIA_2, Camera
from test_https import Lancement, _port_libre

CHEMINS_DAHUA = "/cam/realmonitor?channel=1&subtype=0,/cam/realmonitor?channel=1&subtype=1"


def _services(env: dict[str, str]) -> set[str]:
    port = _port_libre()
    with Lancement({"ONVIF_PORT": str(port)} | env):
        return set(Camera(f"http://127.0.0.1:{port}", None).services())


def test_sans_variable_ni_image_ni_media_2():
    assert _services({}) == {NS["tds"], NS["trt"]}


def test_image_et_media_2():
    assert _services({"ONVIF_SERVICES": "image,media2"}) >= {NS_IMAGE, NS_MEDIA_2}


def test_media_2_coupe_au_demarrage():
    services = _services({"ONVIF_SERVICES": "image"})

    assert NS_IMAGE in services and NS_MEDIA_2 not in services


def test_un_profil_par_chemin_rtsp():
    port = _port_libre()
    with Lancement({"ONVIF_PORT": str(port), "ONVIF_CHEMINS_RTSP": CHEMINS_DAHUA}):
        camera = Camera(f"http://127.0.0.1:{port}", None)
        uri = camera.media(
            "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport>"
            "<tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
            "<trt:ProfileToken>Profile_2</trt:ProfileToken></trt:GetStreamUri>"
        ).texte(".//trt:MediaUri/tt:Uri")

    assert uri == "rtsp://127.0.0.1/cam/realmonitor?channel=1&subtype=1"


def test_date_incrustee_ecrite_dans_le_fichier_relu_par_ffmpeg(tmp_path):
    """`ONVIF_FICHIER_DATE` : la date incrustée, réécrite sans cesse (heure d'usine, fuseau AWST-8 : UTC+8)."""
    port, fichier = _port_libre(), tmp_path / "date.txt"
    with Lancement({"ONVIF_PORT": str(port), "ONVIF_FICHIER_DATE": str(fichier)}):
        fin = time.monotonic() + 5
        while not fichier.exists() and time.monotonic() < fin:
            time.sleep(0.05)
        premiere = fichier.read_text()
        time.sleep(1.2)
        seconde = fichier.read_text()

    attendue = datetime.now(UTC) + timedelta(minutes=7, hours=8)
    lue = datetime.strptime(seconde, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    assert abs((lue - attendue).total_seconds()) <= 2
    assert seconde != premiere
