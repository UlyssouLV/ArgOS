"""Encodage par le média 1 : le repli d'une caméra sans média 2 (Flux H.264). Même encodeur que le média 2."""

from conftest import CHEMINS_RTSP_2, NS

ENCODEUR_PRINCIPAL = "VideoEncoderConfig_1"


def lire_encodeur(camera, token: str = ENCODEUR_PRINCIPAL) -> dict:
    reponse = camera.media("<trt:GetVideoEncoderConfigurations/>")
    assert reponse.statut == 200
    configuration = next(c for c in reponse.xml.findall(".//trt:Configurations", NS) if c.get("token") == token)
    return {
        "codec": configuration.findtext("tt:Encoding", namespaces=NS),
        "resolution": (
            configuration.findtext("tt:Resolution/tt:Width", namespaces=NS),
            configuration.findtext("tt:Resolution/tt:Height", namespaces=NS),
        ),
        "images_par_seconde": configuration.findtext("tt:RateControl/tt:FrameRateLimit", namespaces=NS),
        "debit": configuration.findtext("tt:RateControl/tt:BitrateLimit", namespaces=NS),
        "qualite": configuration.findtext("tt:Quality", namespaces=NS),
        "gop": configuration.findtext("tt:H264/tt:GovLength", namespaces=NS),
    }


def encodeur(largeur: int, hauteur: int, images: int, debit: int) -> str:
    return (
        f'<trt:Configuration token="{ENCODEUR_PRINCIPAL}"><tt:Name>{ENCODEUR_PRINCIPAL}</tt:Name>'
        "<tt:UseCount>1</tt:UseCount><tt:Encoding>H264</tt:Encoding>"
        f"<tt:Resolution><tt:Width>{largeur}</tt:Width><tt:Height>{hauteur}</tt:Height></tt:Resolution>"
        f"<tt:Quality>4</tt:Quality><tt:RateControl><tt:FrameRateLimit>{images}</tt:FrameRateLimit>"
        f"<tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>{debit}</tt:BitrateLimit></tt:RateControl>"
        "<tt:H264><tt:GovLength>40</tt:GovLength><tt:H264Profile>Main</tt:H264Profile></tt:H264>"
        "<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address>"
        "<tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>"
        "<tt:SessionTimeout>PT60S</tt:SessionTimeout></trt:Configuration>"
    )


def test_profils_avec_leur_encodeur(camera_sans_media_2):
    profils = camera_sans_media_2.media("<trt:GetProfiles/>").xml.findall(".//trt:Profiles", NS)

    assert [p.find("tt:VideoEncoderConfiguration", NS).get("token") for p in profils] == [
        "VideoEncoderConfig_1",
        "VideoEncoderConfig_2",
    ]


def test_url_de_flux_par_profil(camera_sans_media_2):
    uris = [
        camera_sans_media_2.media(
            "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport>"
            f"<tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{profil}"
            "</trt:ProfileToken></trt:GetStreamUri>"
        ).texte(".//trt:MediaUri/tt:Uri")
        for profil in ("Profile_1", "Profile_2")
    ]

    assert uris == [f"rtsp://127.0.0.1{chemin}" for chemin in CHEMINS_RTSP_2]


def test_encodeur_d_usine(camera_sans_media_2):
    assert lire_encodeur(camera_sans_media_2) == {
        "codec": "H264",
        "resolution": ("2304", "1296"),
        "images_par_seconde": "20",
        "debit": "4096",
        "qualite": "4",
        "gop": "40",
    }


def test_options(camera_sans_media_2):
    reponse = camera_sans_media_2.media(
        f"<trt:GetVideoEncoderConfigurationOptions><trt:ConfigurationToken>{ENCODEUR_PRINCIPAL}"
        "</trt:ConfigurationToken></trt:GetVideoEncoderConfigurationOptions>"
    )

    h264 = reponse.trouver(".//trt:Options/tt:H264")
    assert [w.text for w in h264.findall("tt:ResolutionsAvailable/tt:Width", NS)] == ["2304", "1920", "1280"]
    assert (h264.findtext("tt:FrameRateRange/tt:Min", namespaces=NS), h264.findtext("tt:FrameRateRange/tt:Max", namespaces=NS)) == ("1", "22")
    debit = reponse.trouver(".//trt:Options/tt:Extension/tt:H264/tt:BitrateRange")
    assert (debit.findtext("tt:Min", namespaces=NS), debit.findtext("tt:Max", namespaces=NS)) == ("512", "8192")


def test_modification_relue(camera_sans_media_2):
    reponse = camera_sans_media_2.media(
        f"<trt:SetVideoEncoderConfiguration>{encodeur(1280, 720, 10, 1024)}"
        "<trt:ForcePersistence>true</trt:ForcePersistence></trt:SetVideoEncoderConfiguration>"
    )

    assert reponse.statut == 200 and reponse.faute is None
    relu = lire_encodeur(camera_sans_media_2)
    assert (relu["resolution"], relu["images_par_seconde"], relu["debit"]) == (("1280", "720"), "10", "1024")


def test_hors_bornes_refuse(camera_sans_media_2):
    reponse = camera_sans_media_2.media(
        f"<trt:SetVideoEncoderConfiguration>{encodeur(1280, 720, 10, 100)}"
        "<trt:ForcePersistence>true</trt:ForcePersistence></trt:SetVideoEncoderConfiguration>"
    )

    assert reponse.faute == "ter:ConfigModify"
    assert lire_encodeur(camera_sans_media_2)["debit"] == "4096"


def test_media_1_et_media_2_reglent_le_meme_encodeur(camera_complete):
    camera_complete.media(
        f"<trt:SetVideoEncoderConfiguration>{encodeur(1920, 1080, 12, 3000)}"
        "<trt:ForcePersistence>true</trt:ForcePersistence></trt:SetVideoEncoderConfiguration>"
    )

    configuration = camera_complete.media_2(
        f"<tr2:GetVideoEncoderConfigurations><tr2:ConfigurationToken>{ENCODEUR_PRINCIPAL}</tr2:ConfigurationToken>"
        "</tr2:GetVideoEncoderConfigurations>"
    ).trouver(".//tr2:Configurations")
    assert configuration.findtext("tt:Resolution/tt:Width", namespaces=NS) == "1920"
    assert configuration.findtext("tt:RateControl/tt:BitrateLimit", namespaces=NS) == "3000"
