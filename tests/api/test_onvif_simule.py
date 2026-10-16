"""Caméras simulées ONVIF (simulation/onvif/) : qui répond en SOAP, et sur quel port, vu du conteneur `api`.

La 2 répond en HTTPS sur `443` et en HTTP sur `8899`, la 4 en HTTP sur `80`, à l'IP de leur Caméra simulée ; les 1
et 3 ne répondent sur aucun port ONVIF courant. Le détail des opérations est testé avec le simulateur (test-root
simulation/onvif/).
"""

import json

from stack_compose import IPS_SIMULEES, compose, remettre_onvif_en_usine

PORTS_COURANTS = (80, 8899, 2000, 8000, 8080)

# Lancé dans `api` : pour chaque (schéma, IP, port), le statut HTTP d'un GetSystemDateAndTime sans identifiants,
# s'il revient en SOAP, sinon None. Certificat auto-signé de la simulation accepté sans vérification.
SONDE = """
import json, ssl, sys, urllib.error, urllib.request
CORPS = (b'<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body>'
         b'<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></env:Body></env:Envelope>')
CONTEXTE = ssl._create_unverified_context()
def sonder(schema, ip, port):
    requete = urllib.request.Request(f"{schema}://{ip}:{port}/onvif/device_service", data=CORPS,
                                     headers={"Content-Type": "application/soap+xml"})
    try:
        with urllib.request.urlopen(requete, timeout=2, context=CONTEXTE) as reponse:
            corps = reponse.read()
            return reponse.status if b"GetSystemDateAndTimeResponse" in corps else None
    except Exception:
        return None
print(json.dumps({f"{s}://{ip}:{port}": sonder(s, ip, port) for s, ip, port in json.loads(sys.argv[1])}))
"""

# Lancé dans `api` : le certificat (DER, en hexadécimal) présenté en HTTPS à (IP, port).
CERTIFICAT = """
import socket, ssl, sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=5) as brut:
    with ssl._create_unverified_context().wrap_socket(brut) as tls:
        print(tls.getpeercert(binary_form=True).hex())
"""


def sonder(*adresses: tuple[str, str, int]) -> dict[str, int | None]:
    return json.loads(compose("exec", "-T", "api", "python", "-c", SONDE, json.dumps(adresses)).stdout)


def certificat_presente(ip: str, port: int) -> str:
    return compose("exec", "-T", "api", "python", "-c", CERTIFICAT, ip, str(port)).stdout.strip()


def test_cameras_simulees_2_et_4_repondent_en_onvif():
    reponses = sonder(("https", IPS_SIMULEES[2], 443), ("http", IPS_SIMULEES[2], 8899), ("http", IPS_SIMULEES[4], 80))

    assert reponses == {
        f"https://{IPS_SIMULEES[2]}:443": 200,
        f"http://{IPS_SIMULEES[2]}:8899": 200,
        f"http://{IPS_SIMULEES[4]}:80": 200,
    }


def test_camera_simulee_4_sans_https():
    assert sonder(("https", IPS_SIMULEES[4], 443)) == {f"https://{IPS_SIMULEES[4]}:443": None}


def test_certificat_de_la_camera_simulee_2_garde_d_un_demarrage_a_l_autre():
    avant = certificat_presente(IPS_SIMULEES[2], 443)

    remettre_onvif_en_usine()

    assert avant and certificat_presente(IPS_SIMULEES[2], 443) == avant


def test_cameras_simulees_1_et_3_sans_onvif():
    adresses = [("http", IPS_SIMULEES[n], port) for n in (1, 3) for port in PORTS_COURANTS] + [
        ("https", IPS_SIMULEES[n], 443) for n in (1, 3)
    ]

    reponses = sonder(*adresses)

    assert reponses == {f"{s}://{ip}:{port}": None for s, ip, port in adresses}
