"""Horloge de la Caméra simulée : « sortie d'usine » au démarrage, puis réglée et relue."""

from datetime import UTC, datetime

LIRE_HORLOGE = "<tds:GetSystemDateAndTime/>"


def heure_utc(reponse) -> datetime:
    utc = ".//tds:SystemDateAndTime/tt:UTCDateTime"
    champs = [f"{utc}/tt:Date/tt:{c}" for c in ("Year", "Month", "Day")]
    champs += [f"{utc}/tt:Time/tt:{c}" for c in ("Hour", "Minute", "Second")]
    return datetime(*(int(reponse.texte(champ)) for champ in champs), tzinfo=UTC)


def test_horloge_d_usine_au_31_decembre_1999_en_manuel_fuseau_awst(camera):
    reponse = camera.appeler(LIRE_HORLOGE)

    assert reponse.statut == 200
    assert reponse.texte(".//tt:DateTimeType") == "Manual"
    assert reponse.texte(".//tt:TimeZone/tt:TZ") == "AWST-8"
    assert heure_utc(reponse).date() == datetime(1999, 12, 31).date()


def test_serveur_ntp_d_usine(camera):
    reponse = camera.appeler("<tds:GetNTP/>")

    assert reponse.statut == 200
    assert reponse.texte(".//tds:NTPInformation/tt:FromDHCP") == "false"
    assert reponse.texte(".//tt:NTPManual/tt:DNSname") == "NTP"


def test_horloge_reglee_relue_a_l_identique_et_qui_avance(camera):
    reglage = camera.appeler(
        "<tds:SetSystemDateAndTime>"
        "<tds:DateTimeType>Manual</tds:DateTimeType><tds:DaylightSavings>true</tds:DaylightSavings>"
        "<tds:TimeZone><tt:TZ>CET-1CEST,M3.5.0,M10.5.0/3</tt:TZ></tds:TimeZone>"
        "<tds:UTCDateTime><tt:Date><tt:Year>2026</tt:Year><tt:Month>10</tt:Month><tt:Day>13</tt:Day></tt:Date>"
        "<tt:Time><tt:Hour>8</tt:Hour><tt:Minute>30</tt:Minute><tt:Second>0</tt:Second></tt:Time></tds:UTCDateTime>"
        "</tds:SetSystemDateAndTime>"
    )
    assert reglage.statut == 200 and reglage.faute is None

    relue = camera.appeler(LIRE_HORLOGE)

    assert relue.texte(".//tt:TimeZone/tt:TZ") == "CET-1CEST,M3.5.0,M10.5.0/3"
    assert relue.texte(".//tt:DaylightSavings") == "true"
    ecart = heure_utc(relue) - datetime(2026, 10, 13, 8, 30, tzinfo=UTC)
    assert 0 <= ecart.total_seconds() <= 5


def test_passage_en_ntp_relu(camera):
    camera.appeler(
        "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
        "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>"
    )

    relue = camera.appeler(LIRE_HORLOGE)

    assert relue.texte(".//tt:DateTimeType") == "NTP"
    # Sans fuseau dans la demande, le fuseau est gardé.
    assert relue.texte(".//tt:TimeZone/tt:TZ") == "AWST-8"


def test_heure_manuelle_sans_date_refusee(camera):
    reponse = camera.appeler(
        "<tds:SetSystemDateAndTime><tds:DateTimeType>Manual</tds:DateTimeType>"
        "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>"
    )

    assert reponse.statut == 400
    assert reponse.faute == "ter:InvalidArgVal"
    assert heure_utc(camera.appeler(LIRE_HORLOGE)).year == 1999
