"""État des Caméras par sonde RTSP, vu de l'extérieur de la stack.

La sonde tourne dans le conteneur `api` : les Caméras simulées s'y déclarent avec
`rtsp://mediamtx:8554/camN`. La requête `?test=…` rend chaque URL unique (l'URL est unique
parmi les Caméras) ; MediaMTX l'ignore.
"""

import time

import httpx

from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)

# Intervalle (10 s) + délai (5 s) de sonde par défaut, avec de la marge.
DELAI_ETAT_S = 40


def url_simulee(chemin: str) -> str:
    return f"rtsp://mediamtx:8554/{chemin}?test={unique('etat')}"


def attendre_etat(client: httpx.Client, id_camera: int, etat: str) -> dict:
    echeance = time.monotonic() + DELAI_ETAT_S
    while True:
        camera = client.get(f"/api/cameras/{id_camera}").json()
        if camera["etat"] == etat:
            return camera
        assert time.monotonic() < echeance, f"Caméra toujours {camera['etat']!r}, {etat!r} attendu"
        time.sleep(0.5)


def test_camera_simulee_online_et_horodatee(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee("cam1")).json()

    sondee = attendre_etat(connecte, camera["id"], "online")

    assert sondee["etat_verifie_le"] is not None


def test_url_injoignable_offline(connecte, creer_camera):
    camera = creer_camera(url_rtsp=f"rtsp://{unique('hote')}.invalid/flux").json()

    assert attendre_etat(connecte, camera["id"], "offline")["etat_verifie_le"] is not None


def test_chemin_mediamtx_inexistant_offline(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee("cam404")).json()

    assert attendre_etat(connecte, camera["id"], "offline")["etat_verifie_le"] is not None


def test_changement_d_url_unknown_puis_nouvel_etat(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee("cam1")).json()
    attendre_etat(connecte, camera["id"], "online")

    modifiee = connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": url_simulee("cam404")})

    assert modifiee.status_code == 200
    assert modifiee.json()["etat"] == "unknown"
    assert modifiee.json()["etat_verifie_le"] is None
    attendre_etat(connecte, camera["id"], "offline")


def test_camera_desactivee_unknown_et_plus_sondee(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee("cam1")).json()
    attendre_etat(connecte, camera["id"], "online")

    desactivee = connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False})
    # Au-delà d'un cycle de sonde complet : une sonde aurait eu le temps de repasser.
    time.sleep(16)

    assert desactivee.json()["etat"] == "unknown"
    assert connecte.get(f"/api/cameras/{camera['id']}").json() == desactivee.json()
