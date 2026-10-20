"""Heure du Site et calage des Caméras (docs/adr/0014-serveur-de-temps-du-site.md), vus de l'extérieur de la stack.

La source réglée se vérifie sur ce que `temps` sert vraiment (lu par l'API en NTP) ; le calage, sur les Caméras
simulées ONVIF, qui interrogent vraiment le serveur NTP reçu. Le réglage d'origine est remis tel quel en base après
chaque test qui le change.
"""

import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from stack_compose import compose, remettre_onvif_en_usine, url_camera_simulee
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)

# Adresse de temps sur le réseau des Caméras simulées (compose.simulation.yaml) : celle annoncée aux Caméras.
ADRESSE_TEMPS = "172.30.0.10"
# Adresse de documentation (RFC 5737) : jamais joignable.
SOURCE_INJOIGNABLE = "192.0.2.1"
# temps relit son réglage toutes les 2 s, puis interroge sa source.
DELAI_SOURCE_S = 60
DELAI_LECTURE_S = 30
# Une Caméra simulée calée s'interroge aussitôt sur temps : son écart retombe vite.
DELAI_CALAGE_S = 60
ECART_CALE_S = 2
# Horloge d'usine des Caméras simulées ONVIF.
AVANCE_D_USINE_S = 7 * 60
MARGE_USINE_S = 5
COLONNES = ("heure_source", "heure_serveur_ntp", "fuseau")


def psql(requete: str) -> str:
    return compose("exec", "-T", "db", "psql", "-U", "argos", "-d", "argos", "-At", "-c", requete).stdout.strip()


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()
    yield
    remettre_onvif_en_usine()


@pytest.fixture
def heure_d_origine(connecte):
    """Remet l'Heure du Site telle quelle en base (fuseau de l'hôte compris), et la source de temps, après le test."""
    connecte.get("/api/heure-du-site")
    avant = psql(f"SELECT {', '.join(COLONNES)} FROM reglages_site WHERE id = 1").split("|")
    yield
    valeurs = ", ".join(
        f"{colonne} = {'NULL' if valeur == '' and colonne == 'fuseau' else repr(valeur)}"
        for colonne, valeur in zip(COLONNES, avant)
    )
    psql(f"UPDATE reglages_site SET {valeurs} WHERE id = 1")
    source = "" if avant[0] == "horloge_serveur" else avant[1]
    compose("exec", "-T", "api", "sh", "-c", f"printf '%s\\n' '{source}' > /temps/source")


def lire(client) -> dict:
    reponse = client.get("/api/heure-du-site")
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def modifier(client, **champs):
    return client.patch("/api/heure-du-site", json=champs)


def attendre(client, condition, delai_s: float = DELAI_SOURCE_S) -> dict:
    fin = time.monotonic() + delai_s
    while not condition(lue := lire(client)):
        assert time.monotonic() < fin, lue
        time.sleep(1)
    return lue


def horloge(client, id_camera: int) -> dict:
    reponse = client.get(f"/api/cameras/{id_camera}/reglages", timeout=DELAI_LECTURE_S)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()["horloge"]


def attendre_horloge(client, id_camera: int, condition) -> dict:
    fin = time.monotonic() + DELAI_CALAGE_S
    while not condition(lue := horloge(client, id_camera)):
        assert time.monotonic() < fin, lue
        time.sleep(1)
    return lue


@pytest.fixture
def camera_simulee(creer_camera):
    def _creer(numero: int) -> int:
        reponse = creer_camera(url_rtsp=url_camera_simulee(numero, unique("heure")))
        assert reponse.status_code == 201, reponse.text
        return reponse.json()["id"]

    return _creer


# --- Lire, modifier ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("methode", "corps"), [("GET", None), ("PATCH", {"fuseau": "UTC"})])
def test_heure_du_site_sans_session_401(client, methode, corps):
    assert client.request(methode, "/api/heure-du-site", json=corps).status_code == 401


def test_par_defaut_pool_ntp_org_et_fuseau_de_l_hote(connecte, heure_d_origine):
    psql("UPDATE reglages_site SET heure_source = DEFAULT, heure_serveur_ntp = DEFAULT, fuseau = NULL WHERE id = 1")

    lue = lire(connecte)

    assert (lue["source"], lue["serveur_ntp"], lue["fuseau_de_l_hote"]) == ("ntp", "pool.ntp.org", True)
    # Même décalage que l'heure locale de cette machine, hôte de la stack.
    maintenant = datetime.now(UTC)
    assert maintenant.astimezone(ZoneInfo(lue["fuseau"])).utcoffset() == maintenant.astimezone().utcoffset()


def test_heure_servie_par_temps_et_adresse_annoncee(connecte):
    lue = lire(connecte)

    assert lue["adresse_serveur_de_temps"] == ADRESSE_TEMPS
    assert lue["source_utilisee"] in ("ntp", "horloge_serveur", "non_synchronise")
    assert abs((datetime.fromisoformat(lue["heure"]) - datetime.now(UTC)).total_seconds()) < 2


def test_horloge_du_serveur_puis_source_injoignable_puis_pool_ntp_org(connecte, heure_d_origine):
    reponse = modifier(connecte, source="horloge_serveur")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["source"] == "horloge_serveur"
    attendre(connecte, lambda lue: lue["source_utilisee"] == "horloge_serveur")

    # Source injoignable : temps se replie sur l'horloge du serveur.
    assert modifier(connecte, source="ntp", serveur_ntp=SOURCE_INJOIGNABLE).status_code == 200
    lue = attendre(connecte, lambda lue: lue["source_utilisee"] == "horloge_serveur")
    assert (lue["source"], lue["serveur_ntp"], lue["reference"]) == ("ntp", SOURCE_INJOIGNABLE, None)

    assert modifier(connecte, serveur_ntp="pool.ntp.org").status_code == 200
    lue = attendre(connecte, lambda lue: lue["source_utilisee"] == "ntp")
    assert lue["reference"]


def test_fuseau_choisi_n_est_plus_celui_de_l_hote(connecte, heure_d_origine):
    reponse = modifier(connecte, fuseau="Pacific/Noumea")

    assert reponse.status_code == 200
    assert (reponse.json()["fuseau"], reponse.json()["fuseau_de_l_hote"]) == ("Pacific/Noumea", False)
    assert lire(connecte)["fuseau"] == "Pacific/Noumea"


@pytest.mark.parametrize(
    "corps",
    [
        {},
        {"fuseau": "Mars/Olympus"},
        {"fuseau": "../../etc/passwd"},
        {"source": "gps"},
        {"serveur_ntp": ""},
        {"serveur_ntp": "pool.ntp.org iburst\nallow all"},
        {"serveur_ntp": "-x"},
    ],
)
def test_reglage_invalide_422(connecte, corps):
    assert modifier(connecte, **corps).status_code == 422


# --- Calage des Caméras -----------------------------------------------------------------------------------------


def test_camera_onvif_ajoutee_calee_sur_le_site_au_fuseau_du_site(connecte, camera_simulee):
    fuseau = lire(connecte)["fuseau"]

    # camera-simulee-2 : HTTPS, identifiants ; elle démarre 7 minutes en avance, au fuseau AWST-8.
    id_camera = camera_simulee(2)

    calee = horloge(connecte, id_camera)
    assert (calee["mode"], calee["serveur_ntp"], calee["fuseau"]) == ("ntp", ADRESSE_TEMPS, fuseau)
    attendre_horloge(connecte, id_camera, lambda lue: abs(lue["ecart_s"]) < ECART_CALE_S)


def test_changer_le_fuseau_recale_les_cameras_actives(connecte, camera_simulee, heure_d_origine):
    id_camera = camera_simulee(2)
    fuseau = "Indian/Reunion" if lire(connecte)["fuseau"] != "Indian/Reunion" else "Asia/Tokyo"

    assert modifier(connecte, fuseau=fuseau).status_code == 200

    attendre_horloge(connecte, id_camera, lambda lue: lue["fuseau"] == fuseau and lue["mode"] == "ntp")


def test_changer_la_source_recale_une_camera_qui_visait_un_autre_serveur(connecte, camera_simulee, heure_d_origine):
    id_camera = camera_simulee(2)
    # Réglée ailleurs entre-temps : un autre serveur.
    compose(
        "exec", "-T", "api", "python", "-c",
        "from argos_api import onvif; from datetime import datetime, UTC;"
        "onvif.caler('rtsp://admin:argos-simulee@camera-simulee-2/', onvif.Retenu(), 'ntp.example.org', 'UTC0',"
        " lambda: datetime.now(UTC))",
    )
    assert horloge(connecte, id_camera)["serveur_ntp"] == "ntp.example.org"

    assert modifier(connecte, source="horloge_serveur").status_code == 200

    attendre_horloge(connecte, id_camera, lambda lue: lue["serveur_ntp"] == ADRESSE_TEMPS)


def test_camera_sans_onvif_ajoutee_sans_calage_ni_erreur(camera_simulee, connecte):
    # camera-simulee-1 : pas d'ONVIF.
    id_camera = camera_simulee(1)

    assert connecte.get(f"/api/cameras/{id_camera}").json()["port_onvif"] is None


def test_camera_onvif_en_clair_non_accepte_ajoutee_sans_calage(connecte, camera_simulee):
    # camera-simulee-4 : HTTP seulement ; l'ONVIF en clair s'accorde après l'ajout.
    id_camera = camera_simulee(4)
    assert connecte.put(f"/api/cameras/{id_camera}/reglages/onvif-en-clair").status_code == 204

    usine = horloge(connecte, id_camera)

    assert (usine["mode"], usine["serveur_ntp"]) == ("manuel", "NTP")
    assert abs(usine["ecart_s"] - AVANCE_D_USINE_S) < MARGE_USINE_S
