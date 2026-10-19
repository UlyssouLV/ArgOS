"""Horloge de la Caméra simulée : 7 minutes d'avance au démarrage, réglée et relue, calée sur un serveur NTP."""

import time
from datetime import UTC, datetime

import pytest

LIRE_HORLOGE = "<tds:GetSystemDateAndTime/>"
AVANCE_D_USINE_S = 7 * 60
# Requêtes et secondes tronquées par GetSystemDateAndTime.
MARGE_S = 2
ECART_CALE_S = 2
DELAI_CALAGE_S = 5
# Adresse de documentation (RFC 5737) : jamais joignable.
SERVEUR_INJOIGNABLE = "192.0.2.1"


def heure_utc(reponse) -> datetime:
    utc = ".//tds:SystemDateAndTime/tt:UTCDateTime"
    champs = [f"{utc}/tt:Date/tt:{c}" for c in ("Year", "Month", "Day")]
    champs += [f"{utc}/tt:Time/tt:{c}" for c in ("Hour", "Minute", "Second")]
    return datetime(*(int(reponse.texte(champ)) for champ in champs), tzinfo=UTC)


def ecart_s(camera) -> float:
    """Avance de la caméra sur l'heure réelle, en secondes (secondes tronquées : au plus une de moins)."""
    return (heure_utc(camera.appeler(LIRE_HORLOGE)) - datetime.now(UTC)).total_seconds()


def regler_ntp(camera, adresse: str, type_adresse: str = "IPv4"):
    balise = {"IPv4": "IPv4Address", "IPv6": "IPv6Address", "DNS": "DNSname"}[type_adresse]
    return camera.appeler(
        "<tds:SetNTP><tds:FromDHCP>false</tds:FromDHCP>"
        f"<tds:NTPManual><tt:Type>{type_adresse}</tt:Type><tt:{balise}>{adresse}</tt:{balise}></tds:NTPManual>"
        "</tds:SetNTP>"
    )


def passer_en_ntp(camera, fuseau: str = "CET-1CEST,M3.5.0,M10.5.0/3"):
    return camera.appeler(
        "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
        "<tds:DaylightSavings>false</tds:DaylightSavings>"
        f"<tds:TimeZone><tt:TZ>{fuseau}</tt:TZ></tds:TimeZone></tds:SetSystemDateAndTime>"
    )


def attendre_ecart(camera, condition) -> float:
    fin = time.monotonic() + DELAI_CALAGE_S
    while True:
        ecart = ecart_s(camera)
        if condition(ecart) or time.monotonic() > fin:
            return ecart
        time.sleep(0.1)


def test_horloge_d_usine_en_avance_de_7_minutes_en_manuel_fuseau_awst(camera):
    reponse = camera.appeler(LIRE_HORLOGE)

    assert reponse.statut == 200
    assert reponse.texte(".//tt:DateTimeType") == "Manual"
    assert reponse.texte(".//tt:TimeZone/tt:TZ") == "AWST-8"
    assert abs(ecart_s(camera) - AVANCE_D_USINE_S) <= MARGE_S


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
    assert abs(ecart_s(camera) - AVANCE_D_USINE_S) <= MARGE_S


# --- Calage sur un serveur NTP ----------------------------------------------------------------------------------


def test_set_ntp_puis_mode_ntp_ecart_retombe_sous_2_s(camera_et_serveur_ntp):
    camera, _, serveur = camera_et_serveur_ntp

    assert regler_ntp(camera, "127.0.0.1").faute is None
    assert passer_en_ntp(camera).faute is None

    assert abs(attendre_ecart(camera, lambda e: abs(e) < ECART_CALE_S)) < ECART_CALE_S
    assert serveur.requetes >= 1


def test_suit_l_heure_du_serveur_ntp_pas_celle_de_la_machine(camera_et_serveur_ntp):
    camera, _, serveur = camera_et_serveur_ntp
    serveur.avance = 3600

    regler_ntp(camera, "localhost", "DNS")
    passer_en_ntp(camera)

    assert abs(attendre_ecart(camera, lambda e: abs(e - 3600) < ECART_CALE_S) - 3600) < ECART_CALE_S


def test_get_ntp_et_fuseau_relus_apres_calage(camera_et_serveur_ntp):
    camera, _, _ = camera_et_serveur_ntp

    regler_ntp(camera, "127.0.0.1")
    passer_en_ntp(camera, "CET-1CEST,M3.5.0,M10.5.0/3")

    ntp = camera.appeler("<tds:GetNTP/>")
    assert ntp.texte(".//tds:NTPInformation/tt:FromDHCP") == "false"
    assert ntp.texte(".//tt:NTPManual/tt:Type") == "IPv4"
    assert ntp.texte(".//tt:NTPManual/tt:IPv4Address") == "127.0.0.1"
    horloge = camera.appeler(LIRE_HORLOGE)
    assert horloge.texte(".//tt:DateTimeType") == "NTP"
    assert horloge.texte(".//tt:TimeZone/tt:TZ") == "CET-1CEST,M3.5.0,M10.5.0/3"


def test_serveur_ntp_recu_en_mode_manuel_n_est_pas_interroge(camera_et_serveur_ntp):
    camera, _, serveur = camera_et_serveur_ntp

    regler_ntp(camera, "127.0.0.1")
    time.sleep(0.5)

    assert serveur.requetes == 0
    assert abs(ecart_s(camera) - AVANCE_D_USINE_S) <= MARGE_S


@pytest.mark.parametrize("serveur", [SERVEUR_INJOIGNABLE, "serveur-ntp-inconnu.invalid"])
def test_serveur_ntp_injoignable_heure_gardee_service_qui_repond(camera, serveur):
    regler_ntp(camera, serveur, "IPv4" if serveur == SERVEUR_INJOIGNABLE else "DNS")
    passer_en_ntp(camera)
    # Plus que le délai d'attente d'une réponse NTP.
    time.sleep(2.5)

    reponse = camera.appeler(LIRE_HORLOGE)

    assert reponse.statut == 200
    assert abs(ecart_s(camera) - AVANCE_D_USINE_S) <= MARGE_S


def test_ntp_depuis_le_dhcp_refuse(camera):
    reponse = camera.appeler("<tds:SetNTP><tds:FromDHCP>true</tds:FromDHCP></tds:SetNTP>")

    assert reponse.statut == 400
    assert reponse.faute == "ter:InvalidArgVal"
    assert camera.appeler("<tds:GetNTP/>").texte(".//tt:NTPManual/tt:DNSname") == "NTP"


def test_set_ntp_sans_adresse_refuse(camera):
    reponse = camera.appeler(
        "<tds:SetNTP><tds:FromDHCP>false</tds:FromDHCP><tds:NTPManual><tt:Type>IPv4</tt:Type></tds:NTPManual></tds:SetNTP>"
    )

    assert reponse.faute == "ter:InvalidArgVal"


# --- Date incrustée dans le Flux --------------------------------------------------------------------------------


def test_date_incrustee_d_usine_a_l_heure_de_la_camera_au_fuseau_awst(camera_et_serveur_ntp):
    _, simulee, _ = camera_et_serveur_ntp
    # AWST-8 : UTC+8, sans heure d'été.
    attendue = datetime.fromtimestamp(time.time() + AVANCE_D_USINE_S + 8 * 3600, UTC)

    incrustee = datetime.strptime(simulee.date_incrustee(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

    assert abs((incrustee - attendue).total_seconds()) <= MARGE_S


def test_date_incrustee_suit_l_heure_corrigee_et_le_fuseau(camera_et_serveur_ntp):
    camera, simulee, _ = camera_et_serveur_ntp
    regler_ntp(camera, "127.0.0.1")
    # UTC-3 toute l'année.
    passer_en_ntp(camera, "BRT3")
    attendre_ecart(camera, lambda e: abs(e) < ECART_CALE_S)
    attendue = datetime.fromtimestamp(time.time() - 3 * 3600, UTC)

    incrustee = datetime.strptime(simulee.date_incrustee(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

    assert abs((incrustee - attendue).total_seconds()) <= MARGE_S
