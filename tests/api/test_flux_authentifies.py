"""Flux réservés à une session ArgOS (docs/adr/0006-flux-authentifies-par-nginx.md), vus de l'extérieur de la stack.

Sous l'origine HTTPS du Site, WHEP (`/flux/webrtc/…`) et LL-HLS (`/flux/hls/…`) ne sont relayés vers le pont que
pour une session valide : sans elle, `401` à chaque requête, pour tout chemin (`camera-<id>`, `apercu-<jeton>`).
"""

import re
from typing import NamedTuple

import httpx
import pytest

from stack_compose import client_du_site
from test_cameras import connecte, creer_camera  # noqa: F401 (fixtures)
from test_connexion import COOKIE_SESSION, se_connecter
from test_essai import essai  # noqa: F401 (fixture)
from test_etat_cameras import url_simulee
from test_https import OFFRE_SDP
from test_mediamtx_en_pont import CHEMIN_HLS, attendre_playlist

COOKIE_INVALIDE = "jeton-qui-n-existe-pas"


class RequeteDeFlux(NamedTuple):
    """Une requête qu'un lecteur envoie pour lire un Flux ; `corps` est une offre SDP pour WHEP."""

    methode: str
    url: str
    corps: bytes | None = None


def requetes_de_flux(chemin: str) -> list[RequeteDeFlux]:
    """Ce qu'un lecteur demande pour lire un chemin : offre WHEP, playlist et segment HLS."""
    return [
        RequeteDeFlux("POST", f"/flux/webrtc/{chemin}/whep", OFFRE_SDP.encode()),
        RequeteDeFlux("GET", f"{CHEMIN_HLS}/{chemin}/index.m3u8"),
        RequeteDeFlux("GET", f"{CHEMIN_HLS}/{chemin}/seg0.mp4"),
    ]


def statut(requete: RequeteDeFlux, cookie: str | None) -> int:
    """Code HTTP d'une requête de Flux par un client neuf, avec ce cookie de session (ou aucun)."""
    entetes = {"Content-Type": "application/sdp"} if requete.corps else {}
    if cookie is not None:
        entetes["Cookie"] = f"{COOKIE_SESSION}={cookie}"
    with client_du_site() as c:
        return c.request(requete.methode, requete.url, content=requete.corps, headers=entetes).status_code


@pytest.fixture
def cookie_ferme(administrateur) -> str:
    """Cookie d'une session ouverte puis fermée par `DELETE /api/session`."""
    with client_du_site() as c:
        assert se_connecter(c, **administrateur).status_code == 204
        jeton = c.cookies[COOKIE_SESSION]
        assert c.delete("/api/session").status_code == 204
    return jeton


def refusees_sans_session(chemin: str, cookie_ferme: str) -> dict[tuple[RequeteDeFlux, str], int]:
    """Codes HTTP des requêtes de Flux sans cookie, avec un cookie invalide et avec celui d'une session fermée."""
    return {
        (requete, nom): statut(requete, cookie)
        for requete in requetes_de_flux(chemin)
        for nom, cookie in (("sans", None), ("invalide", COOKIE_INVALIDE), ("fermee", cookie_ferme))
    }


def test_flux_d_une_camera_active_401_sans_session(creer_camera, cookie_ferme):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()

    codes = refusees_sans_session(camera["chemin_flux"], cookie_ferme)

    assert set(codes.values()) == {401}, codes


def test_flux_d_un_apercu_401_sans_session(essai, cookie_ferme):
    apercu = essai(1)["apercu"]

    codes = refusees_sans_session(apercu, cookie_ferme)

    assert set(codes.values()) == {401}, codes


def test_un_segment_hls_servi_a_une_session_est_refuse_sans_elle(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(4)).json()
    url_maitresse = f"{CHEMIN_HLS}/{camera['chemin_flux']}/index.m3u8"
    maitresse = attendre_playlist(connecte, url_maitresse)
    (variante,) = [ligne for ligne in maitresse.splitlines() if ligne and not ligne.startswith("#")]
    url_variante = httpx.URL(url_maitresse).join(variante)
    (init,) = re.findall(r'#EXT-X-MAP:URI="([^"]+)"', attendre_playlist(connecte, str(url_variante)))
    url_init = str(url_variante.join(init))
    assert connecte.get(url_init).status_code == 200

    assert statut(RequeteDeFlux("GET", url_init), None) == 401
    assert statut(RequeteDeFlux("GET", str(url_variante)), None) == 401


def test_verification_de_session_401_sans_session_2xx_avec(client, administrateur, cookie_ferme):
    assert client.get("/api/session").status_code == 401
    assert statut(RequeteDeFlux("GET", "/api/session"), COOKIE_INVALIDE) == 401
    assert statut(RequeteDeFlux("GET", "/api/session"), cookie_ferme) == 401

    assert se_connecter(client, **administrateur).status_code == 204

    assert 200 <= client.get("/api/session").status_code < 300
