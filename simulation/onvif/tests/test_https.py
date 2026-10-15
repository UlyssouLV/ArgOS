"""HTTPS : la même caméra en HTTPS et en HTTP, et un certificat stable d'un démarrage à l'autre.

Les lancements par variables d'environnement passent par le module lancé tel qu'en conteneur (`python camera_onvif.py`).
"""

import http.client
import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import IDENTIFIANTS, Camera, certificat_presente

MODULE = Path(__file__).resolve().parents[1] / "camera_onvif.py"
REGLAGE_NTP = (
    "<tds:SetSystemDateAndTime><tds:DateTimeType>NTP</tds:DateTimeType>"
    "<tds:DaylightSavings>false</tds:DaylightSavings></tds:SetSystemDateAndTime>"
)


def _der(chemin: str) -> bytes:
    return ssl.PEM_cert_to_DER_cert(Path(chemin).read_text())


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _attendre(port: int) -> None:
    limite = time.monotonic() + 10
    while time.monotonic() < limite:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"rien n'écoute sur le port {port}")


class Lancement:
    """`python camera_onvif.py` lancé avec ces variables d'environnement, arrêté à la sortie."""

    def __init__(self, env: dict[str, str]) -> None:
        self.env = env

    def __enter__(self) -> "Lancement":
        propre = {k: v for k, v in os.environ.items() if not k.startswith("ONVIF_")}
        self.processus = subprocess.Popen([sys.executable, str(MODULE)], env={**propre, **self.env}, stderr=subprocess.DEVNULL)
        for cle in ("ONVIF_PORT", "ONVIF_PORT_HTTPS"):
            if cle in self.env:
                _attendre(int(self.env[cle]))
        return self

    def __exit__(self, *_) -> None:
        self.processus.terminate()
        self.processus.wait(timeout=5)


def _heure_lue(url: str) -> bool:
    return Camera(url, None).appeler("<tds:GetSystemDateAndTime/>").faute is None


# --- Une seule caméra, deux accès -------------------------------------------------------------------------------


@pytest.mark.parametrize("acces", ["https", "http"])
def test_memes_operations_en_https_et_en_http(camera_https_et_http, acces):
    camera = getattr(camera_https_et_http, acces)

    assert camera.appeler("<tds:GetNTP/>").statut == 200
    assert camera.media("<trt:GetOSDs/>").statut == 200


@pytest.mark.parametrize("acces", ["https", "http"])
def test_identifiants_exiges_en_https_comme_en_http(camera_https_et_http, acces):
    reponse = getattr(camera_https_et_http, acces).appeler("<tds:GetNTP/>", identifiants=("admin", "mauvais"))

    assert reponse.faute == "ter:NotAuthorized"


def test_reglage_en_https_relu_en_http(camera_https_et_http):
    camera_https_et_http.https.appeler(REGLAGE_NTP)

    reponse = camera_https_et_http.http.appeler("<tds:GetSystemDateAndTime/>")

    assert reponse.texte(".//tt:DateTimeType") == "NTP"


def test_adresse_media_annoncee_en_http_meme_jointe_en_https(camera_https_et_http):
    adresse = camera_https_et_http.https.adresse_media()

    assert adresse.startswith("http://127.0.0.1:"), adresse


def test_certificat_fourni_presente(camera_https_et_http):
    port = int(camera_https_et_http.https.url.rpartition(":")[2])

    assert certificat_presente(("127.0.0.1", port)) == _der(camera_https_et_http.certificat)


# --- Lancement par variables d'environnement --------------------------------------------------------------------


def _env_https(dossier: Path, port: int) -> dict[str, str]:
    return {
        "ONVIF_PORT_HTTPS": str(port),
        "ONVIF_CERTIFICAT": str(dossier / "certificat.pem"),
        "ONVIF_CLE": str(dossier / "cle.pem"),
    }


def test_certificat_cree_au_premier_demarrage_puis_garde(tmp_path):
    port = _port_libre()

    with Lancement(_env_https(tmp_path, port)):
        premier = certificat_presente(("127.0.0.1", port))
    with Lancement(_env_https(tmp_path, port)):
        second = certificat_presente(("127.0.0.1", port))

    assert premier == second == _der(str(tmp_path / "certificat.pem"))


def test_nouveau_certificat_seulement_si_le_dossier_est_vide(tmp_path):
    port = _port_libre()
    with Lancement(_env_https(tmp_path, port)):
        premier = certificat_presente(("127.0.0.1", port))
    for fichier in tmp_path.iterdir():
        fichier.unlink()

    with Lancement(_env_https(tmp_path, port)):
        autre = certificat_presente(("127.0.0.1", port))

    assert premier != autre


def test_https_et_http(tmp_path):
    https, http = _port_libre(), _port_libre()

    with Lancement(_env_https(tmp_path, https) | {"ONVIF_PORT": str(http)}):
        assert _heure_lue(f"https://127.0.0.1:{https}")
        assert _heure_lue(f"http://127.0.0.1:{http}")


def test_https_seul(tmp_path):
    https = _port_libre()

    with Lancement(_env_https(tmp_path, https)):
        assert _heure_lue(f"https://127.0.0.1:{https}")
        with pytest.raises((OSError, http.client.HTTPException)):
            _heure_lue(f"http://127.0.0.1:{https}")


def test_http_seul():
    http = _port_libre()

    with Lancement({"ONVIF_PORT": str(http)}):
        assert _heure_lue(f"http://127.0.0.1:{http}")
        with pytest.raises(OSError):
            certificat_presente(("127.0.0.1", http))


def test_https_exige_certificat_et_cle():
    resultat = subprocess.run(
        [sys.executable, str(MODULE)],
        env={**os.environ, "ONVIF_PORT_HTTPS": str(_port_libre()), "ONVIF_CERTIFICAT": "", "ONVIF_CLE": ""},
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert resultat.returncode != 0
    assert "ONVIF_CERTIFICAT" in resultat.stderr


def test_sonde_sur_chaque_port(tmp_path):
    https, http = _port_libre(), _port_libre()
    env = _env_https(tmp_path, https) | {"ONVIF_PORT": str(http)}

    with Lancement(env):
        sonde = subprocess.run([sys.executable, str(MODULE), "sonde"], env={**os.environ, **env}, timeout=10)

    assert sonde.returncode == 0


def test_identifiants_par_variables_d_environnement_en_https(tmp_path):
    https = _port_libre()
    env = _env_https(tmp_path, https) | {"ONVIF_IDENTIFIANT": IDENTIFIANTS[0], "ONVIF_MOT_DE_PASSE": IDENTIFIANTS[1]}

    with Lancement(env):
        camera = Camera(f"https://127.0.0.1:{https}", IDENTIFIANTS)
        assert camera.appeler("<tds:GetNTP/>").statut == 200
        assert camera.appeler("<tds:GetNTP/>", identifiants=None).faute == "ter:NotAuthorized"
