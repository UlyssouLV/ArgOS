"""Caméras simulées ONVIF (simulation/onvif/) : qui répond en SOAP, et sur quel port, vu du conteneur `api`.

La 2 répond sur `8899`, la 4 sur `80`, à l'IP de leur Caméra simulée ; les 1 et 3 ne répondent sur aucun port ONVIF
courant. Le détail des opérations est testé avec le simulateur (test-root simulation/onvif/).
"""

import json

from stack_compose import IPS_SIMULEES, compose

PORTS_COURANTS = (80, 8899, 2000, 8000, 8080)

# Lancé dans `api` : pour chaque (IP, port), le statut HTTP d'un GetSystemDateAndTime sans identifiants, s'il
# revient en SOAP, sinon None.
SONDE = """
import json, sys, urllib.error, urllib.request
CORPS = (b'<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body>'
         b'<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></env:Body></env:Envelope>')
def sonder(ip, port):
    requete = urllib.request.Request(f"http://{ip}:{port}/onvif/device_service", data=CORPS,
                                     headers={"Content-Type": "application/soap+xml"})
    try:
        with urllib.request.urlopen(requete, timeout=2) as reponse:
            corps = reponse.read()
            return reponse.status if b"GetSystemDateAndTimeResponse" in corps else None
    except Exception:
        return None
print(json.dumps({f"{ip}:{port}": sonder(ip, port) for ip, port in json.loads(sys.argv[1])}))
"""


def sonder(*adresses: tuple[str, int]) -> dict[str, int | None]:
    return json.loads(compose("exec", "-T", "api", "python", "-c", SONDE, json.dumps(adresses)).stdout)


def test_cameras_simulees_2_et_4_repondent_en_onvif():
    reponses = sonder((IPS_SIMULEES[2], 8899), (IPS_SIMULEES[4], 80))

    assert reponses == {f"{IPS_SIMULEES[2]}:8899": 200, f"{IPS_SIMULEES[4]}:80": 200}


def test_cameras_simulees_1_et_3_sans_onvif():
    adresses = [(IPS_SIMULEES[n], port) for n in (1, 3) for port in PORTS_COURANTS]

    reponses = sonder(*adresses)

    assert reponses == {f"{ip}:{port}": None for ip, port in adresses}
