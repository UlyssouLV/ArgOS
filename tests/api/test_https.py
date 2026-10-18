"""Le Site servi par une seule origine HTTPS (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md).

Vu de l'hôte, comme un poste qui a installé l'Autorité du Site : le certificat est toujours vérifié contre elle.
"""

import json
import socket
import ssl
import subprocess
import time

import httpx
import pytest

from stack_compose import URL_SITE, autorite_du_site, certificat_presente, compose, contexte_tls, hotes_declares
from test_cameras import connecte, creer_camera  # noqa: F401 (fixtures)
from test_etat_cameras import url_simulee

PORTS_HTTP = (80, 8080)
# Anciens ports en clair de l'API, du HLS et de WHEP : plus publiés, seule l'origine HTTPS y mène.
PORTS_FERMES = (8000, 8888, 8889)
TYPE_AUTORITE = "application/x-x509-ca-cert"
# Un tour de réconciliation du pont (10 s) + démarrage du Flux à la demande, avec de la marge.
DELAI_RELAIS_S = 45

# Offre WebRTC minimale d'un lecteur : une piste vidéo H.264 en réception seule (comme le Live).
OFFRE_SDP = "\r\n".join(
    [
        "v=0",
        "o=- 1 1 IN IP4 127.0.0.1",
        "s=-",
        "t=0 0",
        "a=group:BUNDLE 0",
        "m=video 9 UDP/TLS/RTP/SAVPF 96",
        "c=IN IP4 0.0.0.0",
        "a=mid:0",
        "a=recvonly",
        "a=rtcp-mux",
        "a=ice-ufrag:argos",
        "a=ice-pwd:argosargosargosargosargos",
        "a=fingerprint:sha-256 " + ":".join(["AB"] * 32),
        "a=setup:actpass",
        "a=rtpmap:96 H264/90000",
        "a=fmtp:96 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f",
        "",
    ]
)


@pytest.mark.parametrize("nom", ["localhost", "127.0.0.1", *hotes_declares()])
def test_le_certificat_presente_se_valide_contre_l_autorite_pour_chaque_nom_du_site(nom):
    # Connexion à cette machine, en demandant le Site sous ce nom : comme un poste qui ouvre https://<nom>.
    with socket.create_connection(("localhost", 443), timeout=5) as brut:
        with contexte_tls().wrap_socket(brut, server_hostname=nom) as tls:
            assert tls.version() in ("TLSv1.2", "TLSv1.3")


def test_un_nom_que_le_site_ne_porte_pas_est_refuse():
    with socket.create_connection(("localhost", 443), timeout=5) as brut:
        with pytest.raises(ssl.SSLCertVerificationError):
            contexte_tls().wrap_socket(brut, server_hostname="ailleurs.example")


@pytest.mark.parametrize("port", PORTS_HTTP)
def test_http_redirige_vers_https_meme_hote_meme_chemin(port):
    reponse = httpx.get(f"http://localhost:{port}/administration?vue=1", follow_redirects=False)

    assert reponse.status_code == 301
    assert reponse.headers["location"] == "https://localhost/administration?vue=1"


@pytest.mark.parametrize("url", [*(f"http://localhost:{port}" for port in PORTS_HTTP), URL_SITE])
def test_la_partie_publique_de_l_autorite_est_servie_telle_quelle(url):
    reponse = httpx.get(f"{url}/argos-ca.crt", verify=contexte_tls(), follow_redirects=False)

    assert reponse.status_code == 200
    assert reponse.headers["content-type"] == TYPE_AUTORITE
    assert reponse.text == autorite_du_site()
    assert "PRIVATE KEY" not in reponse.text


def test_la_cle_de_l_autorite_n_est_pas_dans_web():
    conteneur = compose("ps", "-q", "web").stdout.strip()
    montages = json.loads(
        subprocess.run(
            ["docker", "inspect", "-f", "{{json .Mounts}}", conteneur], capture_output=True, text=True, check=True
        ).stdout
    )
    cle = compose("run", "--rm", "--no-deps", "-T", "--entrypoint", "cat", "certificats", "/autorite/autorite.key").stdout
    corps = next(ligne for ligne in cle.splitlines() if not ligne.startswith("-----"))

    assert not any(m.get("Name", "").endswith("_autorite") for m in montages), montages
    assert all(not m["RW"] for m in montages), montages
    trouve = compose("exec", "-T", "web", "sh", "-c", f"grep -rlF '{corps}' /etc /usr /tmp || true").stdout
    assert trouve == ""


def test_api_ne_recoit_que_le_certificat_presente_par_le_site():
    conteneur = compose("ps", "-q", "api").stdout.strip()
    montages = json.loads(
        subprocess.run(
            ["docker", "inspect", "-f", "{{json .Mounts}}", conteneur], capture_output=True, text=True, check=True
        ).stdout
    )
    lisibles = compose("exec", "-T", "api", "sh", "-c", "ls /etc/argos").stdout.split()
    presente = compose("exec", "-T", "api", "cat", "/etc/argos/serveur.crt").stdout

    assert not any(m.get("Name", "").endswith("_autorite") for m in montages), montages
    # Certificat du Site en lecture seule ; le volume d'enregistrement est RW (indicateur + purge, ADR 0011).
    assert all(
        not m["RW"] for m in montages if m.get("Destination") != "/enregistrements"
    ), montages
    assert any(m.get("Destination") == "/enregistrements" and m["RW"] for m in montages), montages
    assert lisibles == ["serveur.crt"]
    assert ssl.PEM_cert_to_DER_cert(presente) == certificat_presente()


def test_l_ui_est_servie_par_l_origine_https(client):
    reponse = client.get("/live")

    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]


def test_l_api_est_servie_sous_api_par_l_origine_https(client):
    assert client.get("/api/moi").status_code == 401


@pytest.mark.parametrize("port", PORTS_FERMES)
def test_les_anciens_ports_en_clair_ne_repondent_plus(port):
    with pytest.raises(OSError):
        socket.create_connection(("localhost", port), timeout=2).close()


@pytest.mark.parametrize("origine", ["https://localhost", "http://localhost:5173", "http://site-tiers.example"])
def test_aucune_reponse_de_l_api_ne_porte_d_en_tete_cors(client, origine):
    simple = client.get("/api/moi", headers={"Origin": origine})
    preflight = client.options(
        "/api/session",
        headers={"Origin": origine, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )

    assert "access-control-allow-origin" not in simple.headers
    assert "access-control-allow-origin" not in preflight.headers


def test_whep_accepte_une_offre_sdp_par_l_origine_https_puis_ferme_la_session(connecte, creer_camera):
    camera = creer_camera(url_rtsp=url_simulee(1)).json()
    echeance = time.monotonic() + DELAI_RELAIS_S
    while True:
        reponse = connecte.post(
            f"/flux/webrtc/{camera['chemin_flux']}/whep",
            content=OFFRE_SDP,
            headers={"Content-Type": "application/sdp"},
        )
        if reponse.status_code == 201:
            break
        assert time.monotonic() < echeance, f"WHEP : {reponse.status_code} {reponse.text}"
        time.sleep(1)

    assert reponse.text.startswith("v=0")
    # Session WHEP sous la même origine, à son chemin relayé.
    session = httpx.URL(URL_SITE).join(reponse.headers["location"])
    assert session.host == "localhost" and session.scheme == "https", session
    assert session.path.startswith(f"/flux/webrtc/{camera['chemin_flux']}/whep/"), session
    assert connecte.delete(session).status_code == 200


# Le certificat serveur remplacé par le service certificats, stack jamais arrêtée (#68) : web le sert ensuite.
IP_FICTIVE = "10.9.9.9"
# nginx vérifie son certificat toutes les 2 s, avec de la marge.
DELAI_RECHARGEMENT_S = 15


def _certificat_du_volume() -> bytes:
    pem = compose(
        "run", "--rm", "--no-deps", "-T", "--entrypoint", "cat", "certificats", "/certificats-serveur/public/serveur.crt"
    ).stdout
    return ssl.PEM_cert_to_DER_cert(pem)


def _attendre_certificat_servi(attendu: bytes) -> bytes:
    limite = time.monotonic() + DELAI_RECHARGEMENT_S
    while (servi := certificat_presente()) != attendu and time.monotonic() < limite:
        time.sleep(0.5)
    return servi


def test_une_ip_du_site_changee_est_servie_des_la_fin_du_lancement_sans_arret_de_la_stack():
    avant = certificat_presente()
    try:
        compose("up", "-d", "--wait", env={"MTX_WEBRTCADDITIONALHOSTS": IP_FICTIVE})

        assert certificat_presente() == _certificat_du_volume() != avant
    finally:
        compose("up", "-d", "--wait")


def _demarrage_de_web() -> str:
    conteneur = compose("ps", "-q", "web").stdout.strip()
    return subprocess.run(
        ["docker", "inspect", "-f", "{{.State.StartedAt}}", conteneur], capture_output=True, text=True, check=True
    ).stdout


def test_un_certificat_serveur_remplace_est_servi_sans_redemarrer_web():
    demarre = _demarrage_de_web()
    try:
        compose("run", "--rm", "--no-deps", "-T", "certificats", env={"MTX_WEBRTCADDITIONALHOSTS": IP_FICTIVE})
        attendu = _certificat_du_volume()

        assert _attendre_certificat_servi(attendu) == attendu
        assert _demarrage_de_web() == demarre
    finally:
        compose("run", "--rm", "--no-deps", "-T", "certificats")
        _attendre_certificat_servi(_certificat_du_volume())
