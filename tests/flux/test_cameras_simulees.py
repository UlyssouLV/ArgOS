"""Les Caméras simulées, vues comme de vraies caméras depuis le réseau Compose : RTSP sur le port 554.

Elles ne sont pas publiées sur la machine hôte : ffprobe tourne dans un conteneur rattaché à leur réseau.
"""

import json
import subprocess

import pytest

from conftest import (
    CAMERAS_SIMULEES,
    CHEMINS,
    FICHIER_PROD,
    FICHIER_SIMULATION,
    IDENTIFIANTS,
    RESEAU_SIMULATION,
    REPO_ROOT,
    SOUS_RESEAU_SIMULATION,
    compose,
    configuration,
)

IMAGE_FFPROBE = "linuxserver/ffmpeg:version-7.1-cli"


def url(camera: str, chemin: str | None = None, identifiants: str | None = None) -> str:
    return f"rtsp://{identifiants + '@' if identifiants else ''}{camera}:554/{chemin or CHEMINS[camera]}"


def ffprobe(reseau: str, url_rtsp: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", reseau,
            "--entrypoint", "ffprobe",
            IMAGE_FFPROBE,
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-select_streams", "v:0",
            "-count_frames",
            "-read_intervals", "%+#60",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames",
            "-of", "json",
            url_rtsp,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("camera", CAMERAS_SIMULEES)
def test_diffuse_du_h264_1280x720_decodable(reseau_simulation, camera):
    resultat = ffprobe(reseau_simulation, url(camera, identifiants=IDENTIFIANTS.get(camera)))

    assert resultat.returncode == 0, resultat.stderr
    (flux,) = json.loads(resultat.stdout)["streams"]
    assert flux["codec_name"] == "h264"
    assert (flux["width"], flux["height"]) == (1280, 720)
    assert int(flux["nb_read_frames"]) >= 1


def test_camera_simulee_2_refusee_sans_identifiants(reseau_simulation):
    resultat = ffprobe(reseau_simulation, url("camera-simulee-2"))

    assert resultat.returncode != 0
    assert "401" in resultat.stderr, resultat.stderr


def test_camera_simulee_2_refusee_avec_un_mauvais_mot_de_passe(reseau_simulation):
    resultat = ffprobe(reseau_simulation, url("camera-simulee-2", identifiants="admin:faux"))

    assert resultat.returncode != 0
    assert "401" in resultat.stderr, resultat.stderr


@pytest.mark.parametrize("chemin", ["inconnu", "flux"])
def test_un_seul_chemin_par_camera_simulee(reseau_simulation, chemin):
    resultat = ffprobe(reseau_simulation, url("camera-simulee-1", chemin=chemin))

    assert resultat.returncode != 0
    assert "Server returned 4" in resultat.stderr, resultat.stderr


def test_aucune_camera_simulee_n_a_de_port_publie():
    conteneurs = [json.loads(ligne) for ligne in compose("ps", "--format", "json").splitlines() if ligne]
    publies = {
        c["Service"]: [p for p in c["Publishers"] if p.get("PublishedPort")]
        for c in conteneurs
        if c["Service"] in CAMERAS_SIMULEES
    }

    assert sorted(publies) == CAMERAS_SIMULEES
    assert all(not ports for ports in publies.values()), publies


def test_reseau_de_simulation_a_sous_reseau_fixe_rejoint_par_api_et_pont():
    config = configuration(FICHIER_PROD, FICHIER_SIMULATION)

    (ipam,) = config["networks"][RESEAU_SIMULATION]["ipam"]["config"]
    assert ipam["subnet"] == SOUS_RESEAU_SIMULATION
    for service in [*CAMERAS_SIMULEES, "api", "mediamtx"]:
        assert RESEAU_SIMULATION in config["services"][service]["networks"], service


def test_la_simulation_complete_les_sous_reseaux_de_la_detection():
    environnement = configuration(FICHIER_PROD, FICHIER_SIMULATION)["services"]["api"]["environment"]

    assert environnement["ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX"].split(",")[-1] == SOUS_RESEAU_SIMULATION


def test_la_prod_ne_contient_aucune_trace_de_simulation():
    config = configuration(FICHIER_PROD)
    mediamtx = (REPO_ROOT / "media" / "mediamtx.yml").read_text()

    assert not [s for s in config["services"] if s.startswith("camera-simulee")]
    assert RESEAU_SIMULATION not in config.get("networks", {})
    assert SOUS_RESEAU_SIMULATION not in json.dumps(config)
    assert "paths:" not in mediamtx
    assert "ffmpeg" not in mediamtx
