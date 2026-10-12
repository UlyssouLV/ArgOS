"""Doublons à l'ajout reconnus par la MAC de l'Appareil, même à une autre IP, vus de l'extérieur de la stack.

Même MAC et même chemin qu'une Caméra : `409` comme l'IP:port en 0.4.1. Même MAC, autre chemin (Appareil
à plusieurs Caméras) : le Flux est trouvé avec `appareil_deja_connu`, l'ajout reste permis. Chaque test remet
les Caméras simulées à leur adresse d'origine.
"""

from stack_compose import IPS_SIMULEES, MACS_SIMULEES
from test_cameras import connecte, unique  # noqa: F401 (fixtures)
from test_essai import DELAI_ESSAI_S, essai  # noqa: F401 (fixture)
from test_suivi_adresse import IP_SANS_APPAREIL, ajouter, correspondante, deplacer  # noqa: F401 (fixture)

# Adresse libre du sous-réseau de simulation, hors de la plage dynamique et des autres tests.
NOUVELLE_IP = "172.30.0.24"
# Autre voie du même Appareil Hikvision : camera-simulee-1 ne sert que la voie 101.
AUTRE_CHEMIN = "/Streaming/Channels/201"


def test_appareil_deplace_essaye_au_meme_chemin_409_avec_la_camera(connecte, essai, deplacer):
    camera = ajouter(essai, 1)
    connecte.delete("/api/essai")
    deplacer({1: NOUVELLE_IP})

    reponse = connecte.post("/api/essai", json={"ip": NOUVELLE_IP, "port": 554}, timeout=DELAI_ESSAI_S)

    assert reponse.status_code == 409
    assert reponse.json()["camera"] == correspondante(camera)
    assert reponse.json()["detail"] == f"Déjà configurée : {camera['nom']}"
    # Aucun Aperçu ouvert : rien à renouveler.
    assert connecte.post("/api/essai/renouveler").status_code == 404


def test_meme_appareil_autre_chemin_averti_et_ajout_permis(connecte, essai):
    # L'autre voie de l'Appareil, déclarée à une adresse où l'IP:port ne la rapproche pas.
    camera = ajouter(essai, 1)
    assert camera["url_rtsp"] == f"rtsp://{IPS_SIMULEES[1]}:554/Streaming/Channels/101"
    autre_voie = f"rtsp://{IP_SANS_APPAREIL}:554{AUTRE_CHEMIN}"
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": autre_voie}).status_code == 200

    resultat = essai(1)

    assert resultat["issue"] == "flux_trouve"
    assert resultat["mac"] == MACS_SIMULEES[1]
    assert resultat["appareil_deja_connu"] == correspondante(camera)
    reponse = essai.ajouter(nom=unique("Voie"))
    assert reponse.status_code == 201
    assert reponse.json()["mac"] == MACS_SIMULEES[1]


def test_appareil_inconnu_sans_avertissement(essai):
    resultat = essai(3, chemin="flux")

    assert resultat["issue"] == "flux_trouve"
    assert resultat["appareil_deja_connu"] is None
