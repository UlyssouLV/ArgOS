"""WS-Security : une Caméra simulée avec identifiants refuse toute opération sans eux, sauf la lecture de l'heure."""

import pytest

from conftest import IDENTIFIANTS

OPERATIONS = [
    "<tds:GetNTP/>",
    "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>",
    "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
    "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>",
]


def test_heure_lue_sans_identifiants(camera_protegee):
    reponse = camera_protegee.appeler("<tds:GetSystemDateAndTime/>", identifiants=None)

    assert reponse.statut == 200 and reponse.faute is None


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("identifiants", [None, ("admin", "mauvais"), ("autre", IDENTIFIANTS[1])])
def test_operation_refusee_sans_bons_identifiants(camera_protegee, operation, identifiants):
    reponse = camera_protegee.appeler(operation, identifiants=identifiants)

    assert reponse.statut == 400
    assert reponse.faute == "ter:NotAuthorized"


def test_operation_media_refusee_sans_identifiants(camera_protegee):
    chemin = camera_protegee.chemin_media()

    reponse = camera_protegee.appeler("<trt:GetProfiles/>", chemin=chemin, identifiants=None)

    assert reponse.faute == "ter:NotAuthorized"


def test_reglage_refuse_ne_change_rien(camera_protegee):
    camera_protegee.appeler(OPERATIONS[2], identifiants=("admin", "mauvais"))

    reponse = camera_protegee.appeler("<tds:GetSystemDateAndTime/>")

    assert reponse.texte(".//{http://www.onvif.org/ver10/schema}DateTimeType") == "Manual"


def test_operations_acceptees_avec_les_bons_identifiants(camera_protegee):
    assert camera_protegee.appeler("<tds:GetNTP/>").statut == 200
    assert camera_protegee.media("<trt:GetProfiles/>").statut == 200


def test_operation_inconnue_non_prise_en_charge(camera):
    reponse = camera.appeler("<tds:SetNetworkInterfaces/>")

    assert reponse.statut == 400
    assert reponse.faute == "ter:ActionNotSupported"
