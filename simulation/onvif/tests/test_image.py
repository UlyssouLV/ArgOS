"""Service image de la Caméra simulée 2 : réglages « usine », options, modification relue, WDR accepté sans être appliqué."""

from conftest import IDENTIFIANTS, NS

SOURCE_VIDEO = "VideoSource_1"


def lire_image(camera) -> dict[str, str | None]:
    reponse = camera.image(
        f"<timg:GetImagingSettings><timg:VideoSourceToken>{SOURCE_VIDEO}</timg:VideoSourceToken></timg:GetImagingSettings>"
    )
    assert reponse.statut == 200
    reglages = reponse.trouver(".//timg:ImagingSettings")
    return {
        cle: reglages.findtext(chemin, namespaces=NS)
        for cle, chemin in {
            "contre_jour": "tt:BacklightCompensation/tt:Mode",
            "luminosite": "tt:Brightness",
            "saturation": "tt:ColorSaturation",
            "contraste": "tt:Contrast",
            "infrarouge": "tt:IrCutFilter",
            "nettete": "tt:Sharpness",
            "wdr": "tt:WideDynamicRange/tt:Mode",
            "wdr_niveau": "tt:WideDynamicRange/tt:Level",
        }.items()
    }


def regler_image(camera, reglages: str, identifiants: tuple[str, str] | None = ...):
    return camera.image(
        f"<timg:SetImagingSettings><timg:VideoSourceToken>{SOURCE_VIDEO}</timg:VideoSourceToken>"
        f"<timg:ImagingSettings>{reglages}</timg:ImagingSettings>"
        "<timg:ForcePersistence>true</timg:ForcePersistence></timg:SetImagingSettings>",
        identifiants=identifiants,
    )


def test_reglages_d_usine(camera_complete):
    assert lire_image(camera_complete) == {
        "contre_jour": "OFF",
        "luminosite": "50",
        "saturation": "50",
        "contraste": "50",
        "infrarouge": "AUTO",
        "nettete": "50",
        "wdr": "OFF",
        "wdr_niveau": "50",
    }


def test_options_bornes_et_modes(camera_complete):
    reponse = camera_complete.image(
        f"<timg:GetOptions><timg:VideoSourceToken>{SOURCE_VIDEO}</timg:VideoSourceToken></timg:GetOptions>"
    )

    options = reponse.trouver(".//timg:ImagingOptions")
    for parametre in ("Brightness", "ColorSaturation", "Contrast", "Sharpness", "WideDynamicRange/tt:Level"):
        bornes = (options.findtext(f"tt:{parametre}/tt:{b}", namespaces=NS) for b in ("Min", "Max"))
        assert tuple(bornes) == ("0", "100"), parametre
    assert [m.text for m in options.findall("tt:IrCutFilterModes", NS)] == ["ON", "OFF", "AUTO"]
    assert [m.text for m in options.findall("tt:BacklightCompensation/tt:Mode", NS)] == ["OFF", "ON"]
    assert [m.text for m in options.findall("tt:WideDynamicRange/tt:Mode", NS)] == ["OFF", "ON"]


def test_contre_jour_sans_niveau_borne(camera_complete):
    """Contre-jour : mode seul, sans bornes de niveau (le cas « niveau non proposé »)."""
    reponse = camera_complete.image(
        f"<timg:GetOptions><timg:VideoSourceToken>{SOURCE_VIDEO}</timg:VideoSourceToken></timg:GetOptions>"
    )

    assert reponse.trouver(".//timg:ImagingOptions").find("tt:BacklightCompensation/tt:Level", NS) is None


def test_modification_relue(camera_complete):
    reponse = regler_image(
        camera_complete,
        "<tt:BacklightCompensation><tt:Mode>ON</tt:Mode></tt:BacklightCompensation>"
        "<tt:Brightness>70</tt:Brightness><tt:ColorSaturation>40</tt:ColorSaturation>"
        "<tt:Contrast>65.5</tt:Contrast><tt:IrCutFilter>OFF</tt:IrCutFilter><tt:Sharpness>20</tt:Sharpness>",
    )

    assert reponse.statut == 200 and reponse.faute is None
    assert lire_image(camera_complete) | {"wdr": None, "wdr_niveau": None} == {
        "contre_jour": "ON",
        "luminosite": "70",
        "saturation": "40",
        "contraste": "65.5",
        "infrarouge": "OFF",
        "nettete": "20",
        "wdr": None,
        "wdr_niveau": None,
    }


def test_modification_partielle_garde_le_reste(camera_complete):
    regler_image(camera_complete, "<tt:IrCutFilter>ON</tt:IrCutFilter>")

    image = lire_image(camera_complete)
    assert image["infrarouge"] == "ON" and image["luminosite"] == "50"


def test_wdr_accepte_mais_pas_applique(camera_complete):
    reponse = regler_image(
        camera_complete, "<tt:WideDynamicRange><tt:Mode>ON</tt:Mode><tt:Level>80</tt:Level></tt:WideDynamicRange>"
    )

    assert reponse.statut == 200 and reponse.faute is None
    image = lire_image(camera_complete)
    assert (image["wdr"], image["wdr_niveau"]) == ("OFF", "50")


def test_valeur_hors_bornes_refusee_sans_rien_changer(camera_complete):
    reponse = regler_image(camera_complete, "<tt:Brightness>60</tt:Brightness><tt:Contrast>101</tt:Contrast>")

    assert reponse.faute == "ter:InvalidArgVal"
    assert lire_image(camera_complete)["luminosite"] == "50"


def test_mode_inconnu_refuse(camera_complete):
    reponse = regler_image(camera_complete, "<tt:IrCutFilter>NUIT</tt:IrCutFilter>")

    assert reponse.faute == "ter:InvalidArgVal"


def test_source_video_inconnue_refusee(camera_complete):
    reponse = camera_complete.image(
        "<timg:GetImagingSettings><timg:VideoSourceToken>Autre</timg:VideoSourceToken></timg:GetImagingSettings>"
    )

    assert reponse.faute == "ter:NoSource"


def test_image_refusee_sans_identifiants(camera_complete):
    reponse = camera_complete.image(
        f"<timg:GetOptions><timg:VideoSourceToken>{SOURCE_VIDEO}</timg:VideoSourceToken></timg:GetOptions>",
        identifiants=None,
    )

    assert reponse.faute == "ter:NotAuthorized"


def test_modification_refusee_avec_un_mauvais_mot_de_passe_ne_change_rien(camera_complete):
    reponse = regler_image(camera_complete, "<tt:Brightness>10</tt:Brightness>", identifiants=(IDENTIFIANTS[0], "mauvais"))

    assert reponse.faute == "ter:NotAuthorized"
    assert lire_image(camera_complete)["luminosite"] == "50"
