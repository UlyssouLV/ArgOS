"""État des Caméras par sonde RTSP, vu de l'extérieur de la stack.

La sonde tourne dans le conteneur `api`, rattaché au réseau des Caméras simulées : elles s'y
déclarent comme de vraies caméras, sur leur chemin de vraie caméra (port 554).
"""

import time

import httpx

from stack_compose import url_camera_simulee
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)

# Intervalle (10 s) + délai (5 s) de sonde par défaut, avec de la marge.
DELAI_ETAT_S = 40


def url_simulee(numero: int, chemin: str | None = None, identifiants: bool = True) -> str:
    return url_camera_simulee(numero, unique("etat"), identifiants, chemin)


def attendre_etat(client: httpx.Client, id_camera: int, etat: str) -> dict:
    echeance = time.monotonic() + DELAI_ETAT_S
    while True:
        camera = client.get(f"/api/cameras/{id_camera}").json()
        if camera["etat"] == etat:
            return camera
        assert time.monotonic() < echeance, f"Caméra toujours {camera['etat']!r}, {etat!r} attendu"
        time.sleep(0.5)


def test_camera_simulee_online_et_horodatee(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()

    sondee = attendre_etat(connecte, camera["id"], "online")

    assert sondee["etat_verifie_le"] is not None


def test_url_injoignable_offline(connecte, creer_camera):
    camera = creer_camera(url_rtsp=f"rtsp://{unique('hote')}.invalid/flux").json()

    assert attendre_etat(connecte, camera["id"], "offline")["etat_verifie_le"] is not None


def test_camera_simulee_a_identifiants_online_avec_et_offline_sans(connecte, creer_camera):
    avec = creer_camera(url_rtsp=url_simulee(2)).json()
    sans = creer_camera(url_rtsp=url_simulee(2, identifiants=False)).json()

    attendre_etat(connecte, avec["id"], "online")
    attendre_etat(connecte, sans["id"], "offline")


def test_chemin_inexistant_offline(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1, "inconnu")).json()

    assert attendre_etat(connecte, camera["id"], "offline")["etat_verifie_le"] is not None


def test_changement_d_url_unknown_puis_nouvel_etat(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()
    attendre_etat(connecte, camera["id"], "online")

    modifiee = connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": url_simulee(1, "inconnu")})

    assert modifiee.status_code == 200
    assert modifiee.json()["etat"] == "unknown"
    assert modifiee.json()["etat_verifie_le"] is None
    attendre_etat(connecte, camera["id"], "offline")


def test_camera_desactivee_unknown_et_plus_sondee(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()
    attendre_etat(connecte, camera["id"], "online")

    desactivee = connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False})
    # Au-delà d'un cycle de sonde complet : une sonde aurait eu le temps de repasser.
    time.sleep(16)

    assert desactivee.json()["etat"] == "unknown"
    assert connecte.get(f"/api/cameras/{camera['id']}").json() == desactivee.json()
