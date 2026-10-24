"""Services, profils, fichier de la date incrustée et horloge choisis au lancement (`ONVIF_SERVICES`,
`ONVIF_CHEMINS_RTSP`, `ONVIF_FICHIER_DATE`, `ONVIF_PORT_NTP`, `ONVIF_NTP_PARESSEUX`, `ONVIF_HEURE_MANUELLE_REFUSEE`,
`ONVIF_FUSEAU_DECALAGE_SEUL`),
comme en conteneur."""

import time
from datetime import UTC, datetime, timedelta

from conftest import NS, NS_IMAGE, NS_MEDIA_2, Camera
from test_horloge import ecart_s
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


def test_serveurs_ntp_joints_sur_le_port_choisi(serveur_ntp):
    """`ONVIF_PORT_NTP` : port des serveurs NTP joints ; ailleurs que là où ils répondent, l'horloge reste décalée."""
    port = _port_libre()
    with Lancement({"ONVIF_PORT": str(port), "ONVIF_PORT_NTP": str(serveur_ntp.port)}):
        camera = Camera(f"http://127.0.0.1:{port}", None)
        camera.appeler(
            "<tds:SetNTP><tds:FromDHCP>false</tds:FromDHCP><tds:NTPManual><tt:Type>IPv4</tt:Type>"
            "<tt:IPv4Address>127.0.0.1</tt:IPv4Address></tds:NTPManual></tds:SetNTP>"
        )
        camera.appeler(
            "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
            "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>"
        )
        fin = time.monotonic() + 5
        while serveur_ntp.requetes == 0 and time.monotonic() < fin:
            time.sleep(0.05)

    assert serveur_ntp.requetes >= 1


def test_ntp_paresseux_derive_a_la_vitesse_choisie(serveur_ntp):
    """`ONVIF_NTP_PARESSEUX` : calée une fois sur son serveur, l'horloge dérive ensuite de tant de secondes par heure."""
    port = _port_libre()
    env = {"ONVIF_PORT": str(port), "ONVIF_PORT_NTP": str(serveur_ntp.port), "ONVIF_NTP_PARESSEUX": "7200"}
    with Lancement(env):
        camera = Camera(f"http://127.0.0.1:{port}", None)
        camera.appeler(
            "<tds:SetNTP><tds:FromDHCP>false</tds:FromDHCP><tds:NTPManual><tt:Type>IPv4</tt:Type>"
            "<tt:IPv4Address>127.0.0.1</tt:IPv4Address></tds:NTPManual></tds:SetNTP>"
        )
        camera.appeler(
            "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
            "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>"
        )
        fin = time.monotonic() + 5
        while serveur_ntp.requetes == 0 and time.monotonic() < fin:
            time.sleep(0.05)
        time.sleep(3)
        ecart = ecart_s(camera)

    # 2 s de dérive par seconde : 6 s en 3 s, après un seul calage.
    assert abs(ecart - 6) <= 4
    assert serveur_ntp.requetes == 1


def test_heure_manuelle_refusee_au_lancement():
    """`ONVIF_HEURE_MANUELLE_REFUSEE` : l'heure poussée en mode manuel est refusée d'une faute."""
    port = _port_libre()
    with Lancement({"ONVIF_PORT": str(port), "ONVIF_HEURE_MANUELLE_REFUSEE": "1"}):
        reponse = Camera(f"http://127.0.0.1:{port}", None).appeler(
            "<tds:SetSystemDateAndTime><tds:DateTimeType>Manual</tds:DateTimeType>"
            "<tds:DaylightSavings>false</tds:DaylightSavings><tds:UTCDateTime><tt:Date><tt:Year>2026</tt:Year>"
            "<tt:Month>10</tt:Month><tt:Day>13</tt:Day></tt:Date><tt:Time><tt:Hour>8</tt:Hour><tt:Minute>30</tt:Minute>"
            "<tt:Second>0</tt:Second></tt:Time></tds:UTCDateTime></tds:SetSystemDateAndTime>"
        )

    assert reponse.faute == "ter:InvalidArgVal"


def test_fuseau_decalage_seul_au_lancement():
    """`ONVIF_FUSEAU_DECALAGE_SEUL` : la caméra ne garde que le nom et le décalage du fuseau reçu."""
    port = _port_libre()
    with Lancement({"ONVIF_PORT": str(port), "ONVIF_FUSEAU_DECALAGE_SEUL": "1"}):
        camera = Camera(f"http://127.0.0.1:{port}", None)
        camera.appeler(
            "<tds:SetSystemDateAndTime><tds:DateTimeType>Manual</tds:DateTimeType>"
            "<tds:DaylightSavings>true</tds:DaylightSavings>"
            "<tds:TimeZone><tt:TZ>CET-1CEST,M3.5.0,M10.5.0/3</tt:TZ></tds:TimeZone><tds:UTCDateTime><tt:Date>"
            "<tt:Year>2026</tt:Year><tt:Month>10</tt:Month><tt:Day>13</tt:Day></tt:Date><tt:Time><tt:Hour>8</tt:Hour>"
            "<tt:Minute>30</tt:Minute><tt:Second>0</tt:Second></tt:Time></tds:UTCDateTime></tds:SetSystemDateAndTime>"
        )
        fuseau = camera.appeler("<tds:GetSystemDateAndTime/>").texte(".//tt:TimeZone/tt:TZ")

    assert fuseau == "CET-1"
