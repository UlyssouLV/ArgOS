"""Services et profils choisis au lancement (`ONVIF_SERVICES`, `ONVIF_CHEMINS_RTSP`), comme en conteneur."""

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
