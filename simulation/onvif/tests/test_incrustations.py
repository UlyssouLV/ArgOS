"""Incrustations de la Caméra simulée : « sortie d'usine », modifiées, cachées puis réaffichées."""

from conftest import NS

SOURCE = "VideoSourceConfig_1"


def lire_osds(camera) -> dict[str, dict[str, str]]:
    """Incrustations relues, par type de texte (`Plain` : le nom, `DateAndTime` : la date et l'heure)."""
    reponse = camera.media(f"<trt:GetOSDs><trt:ConfigurationToken>{SOURCE}</trt:ConfigurationToken></trt:GetOSDs>")
    assert reponse.statut == 200
    osds = {}
    for osd in reponse.xml.findall(".//trt:OSDs", NS):
        texte = osd.find("tt:TextString", NS)
        osds[texte.findtext("tt:Type", namespaces=NS)] = {
            "token": osd.get("token"),
            "source": osd.findtext("tt:VideoSourceConfigurationToken", namespaces=NS),
            "position": osd.findtext("tt:Position/tt:Type", namespaces=NS),
            "texte": texte.findtext("tt:PlainText", namespaces=NS),
            "date": texte.findtext("tt:DateFormat", namespaces=NS),
            "heure": texte.findtext("tt:TimeFormat", namespaces=NS),
        }
    return osds


def osd_nom(position: str, texte: str) -> str:
    return (
        f'<tt:VideoSourceConfigurationToken>{SOURCE}</tt:VideoSourceConfigurationToken><tt:Type>Text</tt:Type>'
        f"<tt:Position><tt:Type>{position}</tt:Type></tt:Position>"
        f"<tt:TextString><tt:Type>Plain</tt:Type><tt:PlainText>{texte}</tt:PlainText></tt:TextString>"
    )


def osd_date(position: str) -> str:
    return (
        f'<tt:VideoSourceConfigurationToken>{SOURCE}</tt:VideoSourceConfigurationToken><tt:Type>Text</tt:Type>'
        f"<tt:Position><tt:Type>{position}</tt:Type></tt:Position>"
        "<tt:TextString><tt:Type>DateAndTime</tt:Type>"
        "<tt:DateFormat>yyyy-MM-dd</tt:DateFormat><tt:TimeFormat>HH:mm:ss</tt:TimeFormat></tt:TextString>"
    )


def test_un_profil_sur_une_source_video(camera):
    reponse = camera.media("<trt:GetProfiles/>")

    profils = reponse.xml.findall(".//trt:Profiles", NS)
    assert len(profils) == 1
    assert profils[0].find("tt:VideoSourceConfiguration", NS).get("token") == SOURCE


def test_incrustations_d_usine_nom_en_haut_a_gauche_date_en_bas_a_gauche(camera):
    osds = lire_osds(camera)

    assert osds.keys() == {"Plain", "DateAndTime"}
    assert osds["Plain"] | {"token": None} == {
        "token": None,
        "source": SOURCE,
        "position": "UpperLeft",
        "texte": "CAM01",
        "date": None,
        "heure": None,
    }
    assert (osds["DateAndTime"]["position"], osds["DateAndTime"]["date"], osds["DateAndTime"]["heure"]) == (
        "LowerLeft",
        "yyyy-MM-dd",
        "HH:mm:ss",
    )


def test_options_annoncent_la_creation_des_deux_types(camera):
    reponse = camera.media(
        f"<trt:GetOSDOptions><trt:ConfigurationToken>{SOURCE}</trt:ConfigurationToken></trt:GetOSDOptions>"
    )

    assert reponse.statut == 200
    types = {e.text for e in reponse.xml.findall(".//trt:OSDOptions/tt:TextOption/tt:Type", NS)}
    assert {"Plain", "DateAndTime"} <= types
    positions = {e.text for e in reponse.xml.findall(".//trt:OSDOptions/tt:PositionOption", NS)}
    assert {"UpperLeft", "UpperRight", "LowerLeft", "LowerRight"} <= positions


def test_incrustation_modifiee_relue_a_l_identique(camera):
    token = lire_osds(camera)["Plain"]["token"]

    reponse = camera.media(f'<trt:SetOSD><trt:OSD token="{token}">{osd_nom("LowerRight", "Entrée")}</trt:OSD></trt:SetOSD>')

    assert reponse.statut == 200 and reponse.faute is None
    nom = lire_osds(camera)["Plain"]
    assert (nom["token"], nom["position"], nom["texte"]) == (token, "LowerRight", "Entrée")


def test_incrustation_inconnue_refusee(camera):
    reponse = camera.media(f'<trt:SetOSD><trt:OSD token="inconnue">{osd_nom("UpperLeft", "X")}</trt:OSD></trt:SetOSD>')

    assert reponse.statut == 400
    assert reponse.faute == "ter:InvalidArgVal"


def test_incrustation_cachee_puis_reaffichee(camera):
    token = lire_osds(camera)["DateAndTime"]["token"]

    supprimee = camera.media(f"<trt:DeleteOSD><trt:OSDToken>{token}</trt:OSDToken></trt:DeleteOSD>")

    assert supprimee.statut == 200
    assert lire_osds(camera).keys() == {"Plain"}

    creee = camera.media(f'<trt:CreateOSD><trt:OSD token="">{osd_date("UpperRight")}</trt:OSD></trt:CreateOSD>')

    assert creee.statut == 200
    date = lire_osds(camera)["DateAndTime"]
    assert date["token"] == creee.texte(".//trt:OSDToken")
    assert (date["position"], date["date"], date["heure"]) == ("UpperRight", "yyyy-MM-dd", "HH:mm:ss")


def test_deuxieme_incrustation_du_meme_type_refusee(camera):
    reponse = camera.media(f'<trt:CreateOSD><trt:OSD token="">{osd_nom("UpperRight", "Bis")}</trt:OSD></trt:CreateOSD>')

    assert reponse.statut == 400
    assert reponse.faute == "ter:MaxOSDs"
    assert lire_osds(camera)["Plain"]["texte"] == "CAM01"
