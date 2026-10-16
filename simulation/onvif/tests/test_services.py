"""Services annoncés (`GetServices`) : la Caméra simulée 2 a le service image et le média 2, la 4 ni l'un ni l'autre."""

import urllib.error
import urllib.parse
import urllib.request

import pytest

from conftest import NS, NS_IMAGE, NS_MEDIA_2

NS_APPAREIL = NS["tds"]
NS_MEDIA = NS["trt"]


def test_camera_complete_annonce_image_et_media_2(camera_complete):
    services = camera_complete.services()

    assert services.keys() == {NS_APPAREIL, NS_MEDIA, NS_IMAGE, NS_MEDIA_2}


def test_adresses_annoncees_a_l_hote_joint(camera_complete):
    hote = urllib.parse.urlsplit(camera_complete.url).netloc

    for adresse in camera_complete.services().values():
        assert urllib.parse.urlsplit(adresse).netloc == hote


def test_image_et_media_2_servis_en_https_comme_en_http(camera_https_et_http):
    for camera in (camera_https_et_http.https, camera_https_et_http.http):
        options = "<timg:GetOptions><timg:VideoSourceToken>VideoSource_1</timg:VideoSourceToken></timg:GetOptions>"
        assert camera.image(options).statut == 200
        assert camera.media_2("<tr2:GetProfiles/>").statut == 200


def test_camera_sans_media_2_annonce_l_image_seule(camera_sans_media_2):
    assert camera_sans_media_2.services().keys() == {NS_APPAREIL, NS_MEDIA, NS_IMAGE}


def test_media_2_coupe_n_est_plus_servi(camera_complete, camera_sans_media_2):
    chemin = urllib.parse.urlsplit(camera_complete.services()[NS_MEDIA_2]).path

    with pytest.raises(urllib.error.HTTPError) as erreur:
        urllib.request.urlopen(urllib.request.Request(camera_sans_media_2.url + chemin, data=b""), timeout=5)

    assert erreur.value.code == 404


def test_camera_simple_ni_image_ni_media_2(camera):
    assert camera.services().keys() == {NS_APPAREIL, NS_MEDIA}


def test_capacites_annoncent_l_image(camera_complete, camera):
    capacites = "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"

    assert camera_complete.appeler(capacites).xml.find(".//tt:Imaging/tt:XAddr", NS) is not None
    assert camera.appeler(capacites).xml.find(".//tt:Imaging", NS) is None
