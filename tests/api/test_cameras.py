"""Gestion des Caméras par l'Administrateur, vue de l'extérieur de la stack.

La base n'est jamais effacée : chaque test crée ses Caméras avec des noms et des URL uniques,
puis les désactive et les supprime.
"""

import uuid

import httpx
import pytest

from test_connexion import se_connecter


def unique(prefixe: str) -> str:
    return f"{prefixe}-{uuid.uuid4().hex[:12]}"


def sans_etat(camera: dict) -> dict:
    """La sonde peut changer l'état entre deux requêtes (tests/api/test_etat_cameras.py)."""
    return {cle: valeur for cle, valeur in camera.items() if cle not in ("etat", "etat_verifie_le")}


@pytest.fixture
def connecte(client, administrateur) -> httpx.Client:
    assert se_connecter(client, **administrateur).status_code == 204
    return client


@pytest.fixture
def creer_camera(connecte):
    """Crée des Caméras uniques ; celles qui existent encore à la fin sont désactivées puis supprimées."""
    creees: list[int] = []

    def _creer(**champs) -> httpx.Response:
        corps = {"nom": unique("Caméra"), "url_rtsp": f"rtsp://{unique('hote')}.invalid/flux", **champs}
        reponse = connecte.post("/api/cameras", json=corps)
        if reponse.status_code == 201:
            creees.append(reponse.json()["id"])
        return reponse

    yield _creer

    for id_camera in creees:
        if connecte.patch(f"/api/cameras/{id_camera}", json={"active": False}).status_code == 200:
            assert connecte.delete(f"/api/cameras/{id_camera}").status_code == 204


# Accès


@pytest.mark.parametrize(
    ("methode", "chemin", "corps"),
    [
        ("GET", "/api/cameras", None),
        ("POST", "/api/cameras", {"nom": "Entrée", "url_rtsp": "rtsp://10.0.0.1/flux"}),
        ("GET", "/api/cameras/1", None),
        ("PATCH", "/api/cameras/1", {"nom": "Entrée"}),
        ("DELETE", "/api/cameras/1", None),
    ],
)
def test_routes_cameras_sans_session_401(client, methode, chemin, corps):
    assert client.request(methode, chemin, json=corps).status_code == 401


# Création, liste, lecture


def test_creation_201_unknown_active_hote_et_port_derives(creer_camera):
    nom = unique("Entrée")
    hote = f"{unique('hote')}.invalid"

    reponse = creer_camera(nom=nom, url_rtsp=f"rtsp://{hote}/flux", emplacement="Portail")

    assert reponse.status_code == 201
    camera = reponse.json()
    assert isinstance(camera["id"], int)
    assert camera | {"id": None} == {
        "id": None,
        "nom": nom,
        "url_rtsp": f"rtsp://{hote}/flux",
        "emplacement": "Portail",
        "hote": hote,
        "port": 554,
        "active": True,
        "etat": "unknown",
        "etat_verifie_le": None,
        "chemin_flux": f"camera-{camera['id']}",
    }


def test_port_explicite_de_l_url(creer_camera):
    camera = creer_camera(url_rtsp=f"rtsp://{unique('hote')}.invalid:8554/cam1").json()

    assert camera["port"] == 8554


def test_emplacement_facultatif(creer_camera):
    assert creer_camera().json()["emplacement"] is None


def test_liste_et_lecture(connecte, creer_camera):
    premiere = creer_camera().json()
    seconde = creer_camera().json()

    liste = connecte.get("/api/cameras")
    lue = connecte.get(f"/api/cameras/{premiere['id']}")

    assert liste.status_code == 200
    assert sans_etat(premiere) in [sans_etat(c) for c in liste.json()]
    assert sans_etat(seconde) in [sans_etat(c) for c in liste.json()]
    assert lue.status_code == 200
    assert sans_etat(lue.json()) == sans_etat(premiere)


def test_camera_inexistante_404(connecte, creer_camera):
    id_absent = creer_camera().json()["id"] + 1_000_000

    assert connecte.get(f"/api/cameras/{id_absent}").status_code == 404
    assert connecte.patch(f"/api/cameras/{id_absent}", json={"nom": unique("x")}).status_code == 404
    assert connecte.delete(f"/api/cameras/{id_absent}").status_code == 404


# Doublons et validation


def test_doublon_de_nom_409(creer_camera):
    nom = creer_camera().json()["nom"]

    assert creer_camera(nom=nom).status_code == 409


def test_doublon_d_url_409(creer_camera):
    url = creer_camera().json()["url_rtsp"]

    assert creer_camera(url_rtsp=url).status_code == 409


def test_doublon_face_a_une_camera_desactivee_409(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False}).status_code == 200

    assert creer_camera(nom=camera["nom"]).status_code == 409
    assert creer_camera(url_rtsp=camera["url_rtsp"]).status_code == 409


def test_patch_vers_un_nom_deja_pris_409(connecte, creer_camera):
    prise = creer_camera().json()
    camera = creer_camera().json()

    reponse = connecte.patch(f"/api/cameras/{camera['id']}", json={"nom": prise["nom"]})

    assert reponse.status_code == 409


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/flux",
        "10.0.0.1/flux",
        "rtsp:///flux",
        "rtsp://",
        "rtsp://user:secret@/flux",
    ],
)
def test_url_sans_rtsp_ou_sans_hote_422(creer_camera, url):
    assert creer_camera(url_rtsp=url).status_code == 422


def test_nom_vide_422(creer_camera):
    assert creer_camera(nom="").status_code == 422


# Identifiants RTSP


def test_mot_de_passe_rtsp_masque_en_creation_lecture_et_liste(connecte, creer_camera):
    hote = f"{unique('hote')}.invalid"
    masquee = f"rtsp://user:***@{hote}:8554/flux"

    creee = creer_camera(url_rtsp=f"rtsp://user:secret@{hote}:8554/flux").json()
    lue = connecte.get(f"/api/cameras/{creee['id']}").json()
    listee = next(c for c in connecte.get("/api/cameras").json() if c["id"] == creee["id"])

    assert creee["url_rtsp"] == lue["url_rtsp"] == listee["url_rtsp"] == masquee
    assert creee["hote"] == hote
    assert "secret" not in connecte.get("/api/cameras").text


def test_patch_avec_l_url_masquee_conserve_le_mot_de_passe(connecte, creer_camera):
    url = f"rtsp://user:secret@{unique('hote')}.invalid/flux"
    camera = creer_camera(url_rtsp=url).json()

    reponse = connecte.patch(
        f"/api/cameras/{camera['id']}",
        json={"nom": unique("Renommée"), "url_rtsp": camera["url_rtsp"]},
    )

    assert reponse.status_code == 200
    assert reponse.json()["url_rtsp"] == camera["url_rtsp"]
    # L'URL stockée est toujours celle avec le vrai mot de passe : elle reste réservée.
    assert creer_camera(url_rtsp=url).status_code == 409


# Modification


def test_patch_partiel(connecte, creer_camera):
    camera = creer_camera(emplacement="Portail").json()
    nom = unique("Garage")

    reponse = connecte.patch(f"/api/cameras/{camera['id']}", json={"nom": nom})

    assert reponse.status_code == 200
    assert sans_etat(reponse.json()) == sans_etat(camera | {"nom": nom})


def test_patch_de_l_url_rederive_hote_et_port(connecte, creer_camera):
    camera = creer_camera().json()
    hote = f"{unique('hote')}.invalid"

    reponse = connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": f"rtsp://{hote}:7000/x"})

    assert reponse.status_code == 200
    assert reponse.json() == camera | {
        "url_rtsp": f"rtsp://{hote}:7000/x",
        "hote": hote,
        "port": 7000,
        "etat": "unknown",
        "etat_verifie_le": None,
    }


def test_patch_d_une_url_invalide_422(connecte, creer_camera):
    camera = creer_camera().json()

    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": "http://x/y"}).status_code == 422


# Désactivation, réactivation, suppression


def test_desactivation_puis_reactivation_camera_desactivee_toujours_listee(connecte, creer_camera):
    camera = creer_camera().json()
    chemin = f"/api/cameras/{camera['id']}"

    desactivee = connecte.patch(chemin, json={"active": False})
    listee = next(c for c in connecte.get("/api/cameras").json() if c["id"] == camera["id"])
    reactivee = connecte.patch(chemin, json={"active": True})

    assert desactivee.status_code == 200
    assert desactivee.json() == camera | {
        "active": False,
        "etat": "unknown",
        "etat_verifie_le": None,
        "chemin_flux": None,
    }
    assert listee == desactivee.json()
    assert reactivee.status_code == 200
    assert reactivee.json()["active"] is True


def test_suppression_d_une_camera_active_409(connecte, creer_camera):
    camera = creer_camera().json()

    assert connecte.delete(f"/api/cameras/{camera['id']}").status_code == 409
    assert connecte.get(f"/api/cameras/{camera['id']}").status_code == 200


def test_suppression_d_une_camera_desactivee_204_puis_404(connecte, creer_camera):
    camera = creer_camera().json()
    chemin = f"/api/cameras/{camera['id']}"
    connecte.patch(chemin, json={"active": False})

    assert connecte.delete(chemin).status_code == 204
    assert connecte.get(chemin).status_code == 404
    assert connecte.delete(chemin).status_code == 404

