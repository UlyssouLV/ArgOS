"""Média 2 de la Caméra simulée 2 : profils, URL de flux, configuration d'encodeur et options, modification relue."""

from conftest import CHEMINS_RTSP_2, IDENTIFIANTS, NS

ENCODEUR_PRINCIPAL = "VideoEncoderConfig_1"
ENCODEUR_SECONDAIRE = "VideoEncoderConfig_2"


def lire_encodeurs(camera) -> dict[str, dict]:
    reponse = camera.media_2("<tr2:GetVideoEncoderConfigurations/>")
    assert reponse.statut == 200
    return {
        configuration.get("token"): {
            "codec": configuration.findtext("tt:Encoding", namespaces=NS),
            "resolution": (
                configuration.findtext("tt:Resolution/tt:Width", namespaces=NS),
                configuration.findtext("tt:Resolution/tt:Height", namespaces=NS),
            ),
            "images_par_seconde": configuration.findtext("tt:RateControl/tt:FrameRateLimit", namespaces=NS),
            "debit": configuration.findtext("tt:RateControl/tt:BitrateLimit", namespaces=NS),
            "qualite": configuration.findtext("tt:Quality", namespaces=NS),
            "gop": configuration.get("GovLength"),
        }
        for configuration in reponse.xml.findall(".//tr2:Configurations", NS)
    }


def encodeur(
    token: str, largeur: int, hauteur: int, images: float, debit: int, codec: str = "H264", gop: int = 40
) -> str:
    return (
        f'<tr2:Configuration token="{token}" GovLength="{gop}" Profile="Main">'
        f"<tt:Name>{token}</tt:Name><tt:UseCount>1</tt:UseCount><tt:Encoding>{codec}</tt:Encoding>"
        f"<tt:Resolution><tt:Width>{largeur}</tt:Width><tt:Height>{hauteur}</tt:Height></tt:Resolution>"
        f'<tt:RateControl ConstantBitRate="false"><tt:FrameRateLimit>{images}</tt:FrameRateLimit>'
        f"<tt:BitrateLimit>{debit}</tt:BitrateLimit></tt:RateControl><tt:Quality>4</tt:Quality>"
        "</tr2:Configuration>"
    )


def regler_encodeur(camera, configuration: str, identifiants: tuple[str, str] | None = ...):
    return camera.media_2(
        f"<tr2:SetVideoEncoderConfiguration>{configuration}</tr2:SetVideoEncoderConfiguration>",
        identifiants=identifiants,
    )


def test_deux_profils_sur_une_source_video(camera_complete):
    reponse = camera_complete.media_2("<tr2:GetProfiles><tr2:Type>All</tr2:Type></tr2:GetProfiles>")

    profils = reponse.xml.findall(".//tr2:Profiles", NS)
    assert [p.findtext("tr2:Name", namespaces=NS) for p in profils] == ["mainStream", "subStream"]
    assert [p.find("tr2:Configurations/tr2:VideoSource", NS).get("token") for p in profils] == ["VideoSourceConfig_1"] * 2
    assert [p.find("tr2:Configurations/tr2:VideoEncoder", NS).get("token") for p in profils] == [
        ENCODEUR_PRINCIPAL,
        ENCODEUR_SECONDAIRE,
    ]


def test_url_de_flux_par_profil(camera_complete):
    uris = [
        camera_complete.media_2(
            f"<tr2:GetStreamUri><tr2:Protocol>RTSP</tr2:Protocol><tr2:ProfileToken>{profil}</tr2:ProfileToken>"
            "</tr2:GetStreamUri>"
        ).texte(".//tr2:Uri")
        for profil in ("Profile_1", "Profile_2")
    ]

    assert uris == [f"rtsp://127.0.0.1{chemin}" for chemin in CHEMINS_RTSP_2]


def test_url_de_flux_d_un_profil_inconnu_refusee(camera_complete):
    reponse = camera_complete.media_2(
        "<tr2:GetStreamUri><tr2:Protocol>RTSP</tr2:Protocol><tr2:ProfileToken>Autre</tr2:ProfileToken></tr2:GetStreamUri>"
    )

    assert reponse.faute == "ter:NoProfile"


def test_encodeurs_d_usine(camera_complete):
    assert lire_encodeurs(camera_complete) == {
        ENCODEUR_PRINCIPAL: {
            "codec": "H264",
            "resolution": ("2304", "1296"),
            "images_par_seconde": "20",
            "debit": "4096",
            "qualite": "4",
            "gop": "40",
        },
        ENCODEUR_SECONDAIRE: {
            "codec": "H264",
            "resolution": ("800", "448"),
            "images_par_seconde": "15",
            "debit": "512",
            "qualite": "4",
            "gop": "30",
        },
    }


def test_options_resolutions_images_par_seconde_et_debit(camera_complete):
    reponse = camera_complete.media_2(
        f"<tr2:GetVideoEncoderConfigurationOptions><tr2:ConfigurationToken>{ENCODEUR_PRINCIPAL}"
        "</tr2:ConfigurationToken></tr2:GetVideoEncoderConfigurationOptions>"
    )

    options = reponse.xml.findall(".//tr2:Options", NS)
    assert len(options) == 1
    resolutions = [
        (r.findtext("tt:Width", namespaces=NS), r.findtext("tt:Height", namespaces=NS))
        for r in options[0].findall("tt:ResolutionsAvailable", NS)
    ]
    assert resolutions == [("2304", "1296"), ("1920", "1080"), ("1280", "720")]
    images = [float(i) for i in options[0].get("FrameRatesSupported").split()]
    assert (min(images), max(images)) == (1, 22)
    assert (
        options[0].findtext("tt:BitrateRange/tt:Min", namespaces=NS),
        options[0].findtext("tt:BitrateRange/tt:Max", namespaces=NS),
    ) == ("512", "8192")
    assert options[0].findtext("tt:Encoding", namespaces=NS) == "H264"


def test_options_par_profil(camera_complete):
    reponse = camera_complete.media_2(
        "<tr2:GetVideoEncoderConfigurationOptions><tr2:ProfileToken>Profile_2</tr2:ProfileToken>"
        "</tr2:GetVideoEncoderConfigurationOptions>"
    )

    largeurs = [w.text for w in reponse.xml.findall(".//tr2:Options/tt:ResolutionsAvailable/tt:Width", NS)]
    assert largeurs == ["800", "640", "352"]


def test_modification_relue(camera_complete):
    reponse = regler_encodeur(camera_complete, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 2048))

    assert reponse.statut == 200 and reponse.faute is None
    principal = lire_encodeurs(camera_complete)[ENCODEUR_PRINCIPAL]
    assert (principal["resolution"], principal["images_par_seconde"], principal["debit"]) == (
        ("1920", "1080"),
        "15",
        "2048",
    )
    assert lire_encodeurs(camera_complete)[ENCODEUR_SECONDAIRE]["resolution"] == ("800", "448")


def test_resolution_non_proposee_refusee(camera_complete):
    reponse = regler_encodeur(camera_complete, encodeur(ENCODEUR_PRINCIPAL, 800, 448, 15, 2048))

    assert reponse.faute == "ter:ConfigModify"
    assert lire_encodeurs(camera_complete)[ENCODEUR_PRINCIPAL]["resolution"] == ("2304", "1296")


def test_hors_bornes_refuse(camera_complete):
    assert regler_encodeur(camera_complete, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 25, 2048)).faute == "ter:ConfigModify"
    assert regler_encodeur(camera_complete, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 9000)).faute == "ter:ConfigModify"
    assert lire_encodeurs(camera_complete)[ENCODEUR_PRINCIPAL]["debit"] == "4096"


def test_codec_non_modifiable(camera_complete):
    reponse = regler_encodeur(camera_complete, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 2048, codec="H265"))

    assert reponse.faute == "ter:ConfigModify"


def test_encodeur_inconnu_refuse(camera_complete):
    reponse = regler_encodeur(camera_complete, encodeur("Autre", 1920, 1080, 15, 2048))

    assert reponse.faute == "ter:NoConfig"


def test_media_2_refuse_sans_identifiants(camera_complete):
    assert camera_complete.media_2("<tr2:GetProfiles/>", identifiants=None).faute == "ter:NotAuthorized"


def test_modification_refusee_avec_un_mauvais_mot_de_passe_ne_change_rien(camera_complete):
    reponse = regler_encodeur(
        camera_complete, encodeur(ENCODEUR_PRINCIPAL, 1920, 1080, 15, 2048), identifiants=(IDENTIFIANTS[0], "mauvais")
    )

    assert reponse.faute == "ter:NotAuthorized"
    assert lire_encodeurs(camera_complete)[ENCODEUR_PRINCIPAL]["resolution"] == ("2304", "1296")
