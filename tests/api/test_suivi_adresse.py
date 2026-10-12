"""Suivi d'adresse d'un Appareil à la Détection, vu de l'extérieur de la stack.

Une Caméra simulée déplacée garde sa MAC, comme une vraie caméra après un nouveau bail DHCP
(stack_compose.deplacer_cameras_simulees). La Détection la reconnaît à sa MAC et met à jour l'hôte de
l'URL de ses Caméras. Chaque test remet les Caméras simulées à leur adresse d'origine.
"""

import time

import pytest

from stack_compose import IPS_SIMULEES, MACS_SIMULEES, deplacer_cameras_simulees, remettre_cameras_simulees
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_detection import DELAI_DETECTION_S, candidats_simules
from test_essai import MOT_DE_PASSE_SIMULEE_2, essai  # noqa: F401 (fixture)
from test_etat_cameras import attendre_etat
from test_mediamtx_en_pont import attendre_lisible

# Adresses libres du sous-réseau de simulation, hors de la plage dynamique (compose.simulation.yaml).
NOUVELLES_IPS = {1: "172.30.0.21", 2: "172.30.0.22", 3: "172.30.0.23"}
IP_SANS_APPAREIL = "172.30.0.99"
# Après un déplacement, la table de voisinage d'`api` peut garder l'ancienne MAC d'une IP quelques
# dizaines de secondes : la Détection est relancée jusque-là.
DELAI_VOISINAGE_S = 90


@pytest.fixture
def deplacer():
    yield deplacer_cameras_simulees
    remettre_cameras_simulees()


def ajouter(essai, numero: int) -> dict:
    """Caméra ajoutée depuis l'essai d'une Caméra simulée : URL à son IP, MAC lue."""
    # camera-simulee-2 demande ses identifiants, le chemin exotique de camera-simulee-3 se saisit.
    champs = {2: {"identifiant": "admin", "mot_de_passe": MOT_DE_PASSE_SIMULEE_2}, 3: {"chemin": "flux"}}
    assert essai(numero, **champs.get(numero, {}))["issue"] == "flux_trouve"
    reponse = essai.ajouter(nom=unique("Suivi"))
    assert reponse.status_code == 201
    camera = reponse.json()
    assert camera["mac"] == MACS_SIMULEES[numero]
    return camera


def detecter_jusqu_a(connecte, attendus: dict[str, str]) -> dict[str, dict]:
    """Candidats simulés, par IP, dès que chaque IP de `attendus` répond avec la MAC attendue."""
    echeance = time.monotonic() + DELAI_VOISINAGE_S
    while True:
        reponse = connecte.post("/api/detection", timeout=DELAI_DETECTION_S)
        assert reponse.status_code == 200
        simules = candidats_simules(reponse.json())
        vues = {ip: simules[ip]["mac"] for ip in attendus if ip in simules}
        if vues == attendus:
            return simules
        assert time.monotonic() < echeance, f"MAC vues {vues}, attendues {attendus}"


def lire(connecte, camera: dict) -> dict:
    return connecte.get(f"/api/cameras/{camera['id']}").json()


def correspondante(camera: dict) -> dict:
    return {"id": camera["id"], "nom": camera["nom"]}


def test_camera_deplacee_suivie_hote_seulement_relayee_et_online(connecte, essai, deplacer):
    # Avec identifiants : seul l'hôte change, identifiants, port et chemin gardés.
    camera = ajouter(essai, 2)
    deplacer({2: NOUVELLES_IPS[2]})

    simules = detecter_jusqu_a(connecte, {NOUVELLES_IPS[2]: MACS_SIMULEES[2]})

    candidat = simules[NOUVELLES_IPS[2]]
    assert candidat["camera"] == correspondante(camera)
    assert candidat["adresse_mise_a_jour"] == {"ancienne": IPS_SIMULEES[2], "nouvelle": NOUVELLES_IPS[2]}
    assert candidat["conflit"] is None
    suivie = lire(connecte, camera)
    assert suivie["url_rtsp"] == camera["url_rtsp"].replace(IPS_SIMULEES[2], NOUVELLES_IPS[2])
    assert "admin:***@" in suivie["url_rtsp"]
    assert suivie["mac"] == MACS_SIMULEES[2]
    attendre_etat(connecte, camera["id"], "online")
    attendre_lisible(suivie["chemin_flux"], True)


def test_deux_cameras_qui_echangent_leurs_ip_suivies_par_une_detection(connecte, essai, deplacer):
    premiere, troisieme = ajouter(essai, 1), ajouter(essai, 3)
    deplacer({1: IPS_SIMULEES[3], 3: IPS_SIMULEES[1]})

    simules = detecter_jusqu_a(connecte, {IPS_SIMULEES[3]: MACS_SIMULEES[1], IPS_SIMULEES[1]: MACS_SIMULEES[3]})

    assert simules[IPS_SIMULEES[3]]["camera"] == correspondante(premiere)
    assert simules[IPS_SIMULEES[3]]["adresse_mise_a_jour"] == {"ancienne": IPS_SIMULEES[1], "nouvelle": IPS_SIMULEES[3]}
    assert simules[IPS_SIMULEES[1]]["camera"] == correspondante(troisieme)
    assert simules[IPS_SIMULEES[1]]["adresse_mise_a_jour"] == {"ancienne": IPS_SIMULEES[3], "nouvelle": IPS_SIMULEES[1]}
    assert lire(connecte, premiere)["url_rtsp"] == premiere["url_rtsp"].replace(IPS_SIMULEES[1], IPS_SIMULEES[3])
    assert lire(connecte, troisieme)["url_rtsp"] == troisieme["url_rtsp"].replace(IPS_SIMULEES[3], IPS_SIMULEES[1])


def test_camera_desactivee_suivie_et_toujours_desactivee(connecte, essai, deplacer):
    camera = ajouter(essai, 3)
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"active": False}).status_code == 200
    deplacer({3: NOUVELLES_IPS[3]})

    simules = detecter_jusqu_a(connecte, {NOUVELLES_IPS[3]: MACS_SIMULEES[3]})

    assert simules[NOUVELLES_IPS[3]]["camera"] == correspondante(camera)
    assert simules[NOUVELLES_IPS[3]]["adresse_mise_a_jour"] == {"ancienne": IPS_SIMULEES[3], "nouvelle": NOUVELLES_IPS[3]}
    suivie = lire(connecte, camera)
    assert suivie["url_rtsp"] == camera["url_rtsp"].replace(IPS_SIMULEES[3], NOUVELLES_IPS[3])
    assert suivie["active"] is False


def test_camera_sans_mac_a_l_adresse_d_un_candidat_recoit_sa_mac(connecte, creer_camera):
    camera = creer_camera(url_rtsp=f"rtsp://{IPS_SIMULEES[3]}/flux?test={unique('suivi')}").json()
    assert camera["mac"] is None

    simules = detecter_jusqu_a(connecte, {IPS_SIMULEES[3]: MACS_SIMULEES[3]})

    assert simules[IPS_SIMULEES[3]]["camera"] == correspondante(camera)
    assert simules[IPS_SIMULEES[3]]["adresse_mise_a_jour"] is None
    remplie = lire(connecte, camera)
    assert remplie["mac"] == MACS_SIMULEES[3]
    assert remplie["url_rtsp"] == camera["url_rtsp"]


def test_conflit_avec_une_camera_sans_mac_qui_occupe_l_url(connecte, essai, creer_camera):
    # La Caméra de camera-simulee-1 pointe ailleurs ; une Caméra sans MAC a pris son URL d'origine.
    camera = ajouter(essai, 1)
    ailleurs = camera["url_rtsp"].replace(IPS_SIMULEES[1], IP_SANS_APPAREIL)
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"url_rtsp": ailleurs}).status_code == 200
    occupante = creer_camera(url_rtsp=camera["url_rtsp"]).json()
    assert occupante["mac"] is None

    simules = detecter_jusqu_a(connecte, {IPS_SIMULEES[1]: MACS_SIMULEES[1]})

    candidat = simules[IPS_SIMULEES[1]]
    assert candidat["camera"] == correspondante(camera)
    assert candidat["adresse_mise_a_jour"] is None
    assert candidat["conflit"] == correspondante(occupante)
    assert lire(connecte, camera)["url_rtsp"] == ailleurs
    assert lire(connecte, occupante)["url_rtsp"] == camera["url_rtsp"]


def test_candidat_nouveau_sans_mise_a_jour_ni_conflit(connecte):
    simules = detecter_jusqu_a(connecte, {})

    for candidat in simules.values():
        if candidat["camera"] is None:
            assert candidat["adresse_mise_a_jour"] is None
            assert candidat["conflit"] is None
