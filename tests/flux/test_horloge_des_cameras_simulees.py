"""Horloge des Caméras simulées ONVIF dans la stack : 7 minutes d'avance au démarrage, calée en NTP sur `temps`.

L'interface ONVIF de camera-simulee-4 (HTTP, sans identifiants) est jointe depuis `api`, sur le réseau des Caméras
simulées ; la date incrustée dans son Flux se lit dans le fichier que ffmpeg relit à chaque image.
"""

import time
from ipaddress import ip_address, ip_network
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import FICHIER_PROD, FICHIER_SIMULATION, IPS, RESEAU_SIMULATION, compose, configuration

# IP fixe de temps sur le réseau des Caméras simulées (compose.simulation.yaml).
IP_TEMPS = "172.30.0.10"
ADRESSE_ONVIF = "http://camera-simulee-4:80/onvif/device_service"
FICHIER_DATE = "/horloge/date.txt"
AVANCE_D_USINE_S = 7 * 60
# Secondes tronquées par GetSystemDateAndTime et la date incrustée, plus le temps des requêtes.
MARGE_S = 3
ECART_CALE_S = 2
DELAI_CALAGE_S = 60
NS = {"tds": "http://www.onvif.org/ver10/device/wsdl", "tt": "http://www.onvif.org/ver10/schema"}
# Lancé dans `api` : envoie une enveloppe SOAP et écrit la réponse ; faute SOAP → code de sortie non nul.
_SOAP = """
import sys, urllib.request
adresse, corps = sys.argv[1:]
enveloppe = ('<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"'
             ' xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
             '<env:Body>' + corps + '</env:Body></env:Envelope>')
requete = urllib.request.Request(adresse, data=enveloppe.encode(), headers={"Content-Type": "application/soap+xml"})
sys.stdout.write(urllib.request.urlopen(requete, timeout=5).read().decode())
"""
FUSEAU_PARIS = "CET-1CEST,M3.5.0,M10.5.0/3"


def soap(corps: str) -> ET.Element:
    return ET.fromstring(compose("exec", "-T", "api", "python", "-c", _SOAP, ADRESSE_ONVIF, corps))


def ecart_s() -> float:
    """Avance de la caméra sur l'heure de la machine, au milieu de la requête."""
    avant = datetime.now(UTC)
    utc = soap("<tds:GetSystemDateAndTime/>").find(".//tt:UTCDateTime", NS)
    apres = datetime.now(UTC)
    champs = [f"tt:Date/tt:{c}" for c in ("Year", "Month", "Day")] + [f"tt:Time/tt:{c}" for c in ("Hour", "Minute", "Second")]
    camera = datetime(*(int(utc.findtext(champ, namespaces=NS)) for champ in champs), tzinfo=UTC)
    # Secondes tronquées : une demi-seconde en moyenne.
    return (camera + timedelta(seconds=0.5) - (avant + (apres - avant) / 2)).total_seconds()


def date_incrustee() -> datetime:
    texte = compose("exec", "-T", "camera-simulee-4", "cat", FICHIER_DATE)
    return datetime.strptime(texte, "%Y-%m-%d %H:%M:%S")


@pytest.fixture
def camera_simulee_4_d_usine():
    """Interface ONVIF de camera-simulee-4 relancée « sortie d'usine », avant et après le test."""
    compose("up", "-d", "--force-recreate", "--wait", "camera-simulee-4-onvif")
    yield
    compose("up", "-d", "--force-recreate", "--wait", "camera-simulee-4-onvif")


def test_7_minutes_d_avance_au_demarrage_et_dans_la_date_incrustee(camera_simulee_4_d_usine):
    assert abs(ecart_s() - AVANCE_D_USINE_S) <= MARGE_S
    # Fuseau d'usine AWST-8 : UTC+8.
    attendue = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=8, seconds=AVANCE_D_USINE_S)
    assert abs((date_incrustee() - attendue).total_seconds()) <= MARGE_S


def test_calee_sur_temps_ecart_sous_2_s_et_date_incrustee_corrigee(camera_simulee_4_d_usine):
    soap(
        "<tds:SetNTP><tds:FromDHCP>false</tds:FromDHCP><tds:NTPManual><tt:Type>IPv4</tt:Type>"
        f"<tt:IPv4Address>{IP_TEMPS}</tt:IPv4Address></tds:NTPManual></tds:SetNTP>"
    )
    soap(
        "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
        f"<tds:DaylightSavings>false</tds:DaylightSavings><tds:TimeZone><tt:TZ>{FUSEAU_PARIS}</tt:TZ></tds:TimeZone>"
        "</tds:SetSystemDateAndTime>"
    )

    fin = time.monotonic() + DELAI_CALAGE_S
    while abs(ecart := ecart_s()) >= ECART_CALE_S and time.monotonic() < fin:
        time.sleep(1)

    assert abs(ecart) < ECART_CALE_S
    ntp = soap("<tds:GetNTP/>")
    assert ntp.findtext(".//tt:NTPManual/tt:IPv4Address", namespaces=NS) == IP_TEMPS
    assert soap("<tds:GetSystemDateAndTime/>").findtext(".//tt:TimeZone/tt:TZ", namespaces=NS) == FUSEAU_PARIS
    attendue = datetime.now(ZoneInfo("Europe/Paris")).replace(tzinfo=None)
    assert abs((date_incrustee() - attendue).total_seconds()) <= MARGE_S


def test_temps_a_une_ip_fixe_sur_le_reseau_des_cameras_simulees_hors_des_adresses_dynamiques():
    config = configuration(FICHIER_PROD, FICHIER_SIMULATION)
    (ipam,) = config["networks"][RESEAU_SIMULATION]["ipam"]["config"]

    assert config["services"]["temps"]["networks"][RESEAU_SIMULATION]["ipv4_address"] == IP_TEMPS
    assert ip_address(IP_TEMPS) not in ip_network(ipam["ip_range"])
    assert ip_address(IP_TEMPS) not in {ip_address(ip) for ip in IPS.values()}
