"""Heure du Site, calage, vérification et Mise à l'heure des Caméras (docs/adr/0014-serveur-de-temps-du-site.md,
docs/adr/0015-mise-a-l-heure-a-chaque-verification.md), vus de l'extérieur de la stack.

La source réglée se vérifie sur ce que `temps` sert vraiment (lu par l'API en NTP) ; le calage, la vérification et la
Mise à l'heure, sur les Caméras simulées ONVIF, qui interrogent vraiment le serveur NTP reçu. Le réglage d'origine est remis tel quel en base après
chaque test qui le change.
"""

import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from stack_compose import (
    api_verifiant_les_cameras_toutes_les,
    camera_simulee_2_sans_reponse_ntp,
    compose,
    remettre_onvif_en_usine,
    url_camera_simulee,
)
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
# Vérification de toutes les Caméras actives : 4 à la fois, une caméra muette coûte quelques secondes.
DELAI_VERIFICATION_S = 60
# camera-simulee-5 « NTP paresseux » accélérée : une seconde de dérive par seconde.
DERIVE_PARESSEUSE_S_PAR_H = "3600"
ATTENTE_DERIVE_S = 6
# Secondes tronquées par GetSystemDateAndTime, et le temps des requêtes.
MARGE_DERIVE_S = 3
# Vérification en tâche de fond, raccourcie pour le test (une heure par défaut).
INTERVALLE_VERIFICATION_TEST_S = 5
DELAI_TACHE_DE_FOND_S = 60


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
    def _creer(numero: int, identifiants: bool = True) -> int:
        reponse = creer_camera(url_rtsp=url_camera_simulee(numero, unique("heure"), identifiants))
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


# --- Vérification et Mise à l'heure des Caméras ----------------------------------------------------------------


def caler_ailleurs(serveur: str, fuseau_posix: str) -> None:
    """Règle camera-simulee-2 hors du Site, comme une autre application l'aurait fait entre deux vérifications."""
    compose(
        "exec", "-T", "api", "python", "-c",
        "from argos_api import onvif; from datetime import datetime, UTC;"
        f"onvif.caler('rtsp://admin:argos-simulee@camera-simulee-2/', onvif.Retenu(), {serveur!r}, {fuseau_posix!r},"
        " lambda: datetime.now(UTC))",
    )


def decaler(secondes: float, fuseau_posix: str) -> None:
    """Pousse dans camera-simulee-2 une heure fausse de `secondes`, puis la recale sur le Site : sans réponse NTP, elle
    la garde, comme une caméra calée qui a dérivé."""
    compose(
        "exec", "-T", "api", "python", "-c",
        "from argos_api import onvif; from datetime import datetime, UTC, timedelta;"
        "onvif.mettre_a_l_heure('rtsp://admin:argos-simulee@camera-simulee-2/', onvif.Retenu(),"
        f" {ADRESSE_TEMPS!r}, {fuseau_posix!r}, lambda: datetime.now(UTC) + timedelta(seconds={secondes}))",
    )


def fuseau_posix_du_site(client) -> str:
    """Fuseau POSIX que la Caméra calée a reçu : celui qu'elle relit."""
    return compose(
        "exec", "-T", "api", "python", "-c",
        f"from argos_api import fuseaux; print(fuseaux.posix({lire(client)['fuseau']!r}))",
    ).stdout.strip()


def verifier_maintenant(client) -> dict[int, dict]:
    reponse = client.post("/api/heure-du-site/verification", timeout=DELAI_VERIFICATION_S)
    assert reponse.status_code == 200, reponse.text
    return {camera["id"]: camera for camera in reponse.json()}


def tableau(client) -> dict[int, dict]:
    reponse = client.get("/api/heure-du-site/cameras")
    assert reponse.status_code == 200, reponse.text
    return {camera["id"]: camera for camera in reponse.json()}


def attendre_ligne(client, id_camera: int, condition, delai_s: float = DELAI_TACHE_DE_FOND_S) -> dict:
    fin = time.monotonic() + delai_s
    while not condition(ligne := tableau(client)[id_camera]):
        assert time.monotonic() < fin, ligne
        time.sleep(1)
    return ligne


def recente(date: str | None) -> bool:
    return date is not None and abs((datetime.fromisoformat(date) - datetime.now(UTC)).total_seconds()) < 60


def a_l_heure(ligne: dict) -> bool:
    return ligne["etat"] == "a_l_heure" and abs(ligne["ecart_s"]) <= ECART_CALE_S


def journal(service: str, depuis: str) -> str:
    return compose("logs", "--no-log-prefix", "--since", depuis, service).stdout


@pytest.fixture
def camera_2_sans_reponse_ntp():
    """camera-simulee-2 dont le client NTP n'aboutit jamais : seule la Mise à l'heure la corrige."""
    camera_simulee_2_sans_reponse_ntp()
    yield
    remettre_onvif_en_usine()


@pytest.mark.parametrize(("methode", "chemin"), [("GET", "/cameras"), ("POST", "/verification")])
def test_verification_sans_session_401(client, methode, chemin):
    assert client.request(methode, f"/api/heure-du-site{chemin}").status_code == 401


def test_tableau_des_cameras_actives_avec_leur_derniere_verification(connecte, camera_simulee, creer_camera):
    id_camera = camera_simulee(2)
    desactivee = camera_simulee(1)
    assert connecte.patch(f"/api/cameras/{desactivee}", json={"active": False}).status_code == 200

    lignes = tableau(connecte)

    # Vérifiée dès son ajout : mise à l'heure et calée.
    ligne = lignes[id_camera]
    assert ligne["nom"] == connecte.get(f"/api/cameras/{id_camera}").json()["nom"]
    assert ligne["etat"] in ("a_l_heure", "ecart")
    assert ligne["derive_s"] is not None and ligne["ecart_s"] is not None
    assert recente(ligne["verifiee_le"])
    assert desactivee not in lignes


def test_ajout_mesure_la_derive_et_met_a_l_heure_une_camera_qui_ne_se_synchronise_pas(
    connecte, camera_2_sans_reponse_ntp, camera_simulee
):
    depuis = datetime.now(UTC).isoformat()

    id_camera = camera_simulee(2)

    # Ses 7 minutes d'avance d'usine, mesurées avant la Mise à l'heure ; plus rien après.
    ligne = tableau(connecte)[id_camera]
    assert a_l_heure(ligne), ligne
    assert abs(ligne["derive_s"] - AVANCE_D_USINE_S) < MARGE_USINE_S
    lue = horloge(connecte, id_camera)
    assert (lue["mode"], lue["serveur_ntp"], lue["fuseau"]) == ("ntp", ADRESSE_TEMPS, lire(connecte)["fuseau"])
    recu = journal("camera-simulee-2-onvif", depuis)
    assert "SetSystemDateAndTime" in recu and "SetNTP" in recu


def test_verifier_maintenant_remet_a_l_heure_une_camera_calee_qui_a_derive(
    connecte, camera_2_sans_reponse_ntp, camera_simulee
):
    id_camera = camera_simulee(2)
    decaler(-90, fuseau_posix_du_site(connecte))

    ligne = verifier_maintenant(connecte)[id_camera]

    assert a_l_heure(ligne), ligne
    assert abs(ligne["derive_s"] + 90) < MARGE_USINE_S
    assert recente(ligne["verifiee_le"])
    assert abs(horloge(connecte, id_camera)["ecart_s"]) <= ECART_CALE_S


def test_changer_l_heure_du_site_remet_a_l_heure_les_cameras_actives(
    connecte, camera_2_sans_reponse_ntp, camera_simulee, heure_d_origine
):
    id_camera = camera_simulee(2)
    decaler(150, fuseau_posix_du_site(connecte))
    fuseau = "Indian/Reunion" if lire(connecte)["fuseau"] != "Indian/Reunion" else "Asia/Tokyo"

    assert modifier(connecte, fuseau=fuseau).status_code == 200

    ligne = attendre_ligne(connecte, id_camera, lambda ligne: abs(ligne["derive_s"] - 150) < MARGE_USINE_S)
    assert a_l_heure(ligne), ligne
    assert horloge(connecte, id_camera)["fuseau"] == fuseau


@pytest.fixture
def camera_5_ntp_paresseux():
    """camera-simulee-5 « NTP paresseux », relancée d'usine et qui dérive d'une seconde par seconde."""
    compose(
        "up", "-d", "--force-recreate", "--wait", "camera-simulee-5-onvif",
        env={"ONVIF_NTP_PARESSEUX_5": DERIVE_PARESSEUSE_S_PAR_H},
    )
    yield
    compose("up", "-d", "--force-recreate", "--wait", "camera-simulee-5-onvif")


def test_camera_ntp_paresseux_calee_qui_a_derive_remise_a_l_heure(connecte, camera_5_ntp_paresseux, camera_simulee):
    # camera-simulee-5 : HTTP seulement, sans identifiants ; l'ONVIF en clair s'accorde après l'ajout.
    id_camera = camera_simulee(5)
    assert connecte.put(f"/api/cameras/{id_camera}/reglages/onvif-en-clair").status_code == 204
    debut = time.monotonic()
    assert a_l_heure(verifier_maintenant(connecte)[id_camera])
    # Calée sur le Site, elle ne le réinterroge plus : elle dérive.
    time.sleep(ATTENTE_DERIVE_S)

    ligne = verifier_maintenant(connecte)[id_camera]

    assert a_l_heure(ligne), ligne
    # Une seconde par seconde, entre l'heure poussée à la première vérification et la relecture à la seconde.
    assert ATTENTE_DERIVE_S - MARGE_DERIVE_S < ligne["derive_s"] < time.monotonic() - debut + MARGE_DERIVE_S
    lue = horloge(connecte, id_camera)
    assert (lue["mode"], lue["serveur_ntp"], lue["fuseau"]) == ("ntp", ADRESSE_TEMPS, lire(connecte)["fuseau"])


def test_camera_qui_vise_un_autre_serveur_recalee(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    caler_ailleurs("ntp.example.org", fuseau_posix_du_site(connecte))

    ligne = verifier_maintenant(connecte)[id_camera]

    assert ligne["etat"] in ("a_l_heure", "ecart")
    assert horloge(connecte, id_camera)["serveur_ntp"] == ADRESSE_TEMPS


def test_camera_a_un_autre_fuseau_recalee(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    fuseau = lire(connecte)["fuseau"]
    caler_ailleurs(ADRESSE_TEMPS, "NZST-12NZDT,M9.5.0,M4.1.0/3" if fuseau != "Pacific/Auckland" else "UTC0")

    verifier_maintenant(connecte)

    assert horloge(connecte, id_camera)["fuseau"] == fuseau


def test_mise_a_l_heure_refusee_calee_quand_meme_etat_sur_l_ecart_relu(connecte, camera_simulee):
    # Ni NTP qui aboutisse, ni heure manuelle : elle garde ses 7 minutes d'avance.
    camera_simulee_2_sans_reponse_ntp(heure_manuelle_refusee=True)
    depuis = datetime.now(UTC).isoformat()
    try:
        id_camera = camera_simulee(2)
        caler_ailleurs("ntp.example.org", fuseau_posix_du_site(connecte))

        ligne = verifier_maintenant(connecte)[id_camera]
        lue = horloge(connecte, id_camera)
    finally:
        remettre_onvif_en_usine()

    assert ligne["etat"] == "ecart"
    assert abs(ligne["derive_s"] - AVANCE_D_USINE_S) < MARGE_USINE_S
    assert abs(ligne["ecart_s"] - AVANCE_D_USINE_S) < MARGE_USINE_S
    assert (lue["mode"], lue["serveur_ntp"]) == ("ntp", ADRESSE_TEMPS)
    assert f"Caméra {id_camera} : Mise à l'heure refusée" in journal("api", depuis)


def test_temps_injoignable_calee_quand_meme_en_echec(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    caler_ailleurs("ntp.example.org", fuseau_posix_du_site(connecte))
    depuis = datetime.now(UTC).isoformat()

    compose("stop", "temps")
    try:
        ligne = verifier_maintenant(connecte)[id_camera]
    finally:
        compose("up", "-d", "--wait", "temps")

    assert (ligne["etat"], ligne["derive_s"], ligne["ecart_s"]) == ("echec", None, None)
    assert recente(ligne["verifiee_le"])
    assert horloge(connecte, id_camera)["serveur_ntp"] == ADRESSE_TEMPS
    assert "Serveur de temps du Site injoignable" in journal("api", depuis)


def test_sans_onvif_et_echec_sans_bloquer_les_autres(connecte, camera_simulee):
    sans_onvif = camera_simulee(1)
    # camera-simulee-4 : HTTP seulement, ONVIF en clair non accordé.
    en_clair_non_accorde = camera_simulee(4)
    # camera-simulee-2 sans ses identifiants : elle refuse.
    refusee = camera_simulee(2, identifiants=False)
    calee = camera_simulee(2)
    caler_ailleurs("ntp.example.org", fuseau_posix_du_site(connecte))

    lignes = verifier_maintenant(connecte)

    assert lignes[sans_onvif]["etat"] == "sans_onvif"
    assert lignes[en_clair_non_accorde]["etat"] == "sans_onvif"
    assert lignes[refusee]["etat"] == "echec"
    assert all(
        lignes[i]["derive_s"] is None and lignes[i]["ecart_s"] is None and recente(lignes[i]["verifiee_le"])
        for i in (sans_onvif, refusee)
    )
    assert lignes[calee]["etat"] in ("a_l_heure", "ecart")
    assert horloge(connecte, calee)["serveur_ntp"] == ADRESSE_TEMPS


def test_verifications_d_avant_la_mise_a_jour_lues_a_l_heure_sans_derive(connecte, camera_simulee):
    calee, recalee = camera_simulee(2), camera_simulee(2)
    alembic = ("exec", "-T", "api", "alembic")
    compose(*alembic, "downgrade", "0014")
    try:
        psql(f"UPDATE cameras SET horloge_etat = 'calee', horloge_ecart_s = 0.4 WHERE id = {calee}")
        psql(f"UPDATE cameras SET horloge_etat = 'recalee', horloge_ecart_s = -0.2 WHERE id = {recalee}")
    finally:
        compose(*alembic, "upgrade", "head")

    lignes = tableau(connecte)

    assert (lignes[calee]["etat"], lignes[calee]["derive_s"], lignes[calee]["ecart_s"]) == ("a_l_heure", None, 0.4)
    assert (lignes[recalee]["etat"], lignes[recalee]["derive_s"]) == ("a_l_heure", None)


@pytest.fixture
def verification_raccourcie():
    api_verifiant_les_cameras_toutes_les(INTERVALLE_VERIFICATION_TEST_S)
    yield
    api_verifiant_les_cameras_toutes_les(None)


def test_verification_en_tache_de_fond_sans_rien_demander(verification_raccourcie, connecte, camera_simulee):
    id_camera = camera_simulee(2)
    caler_ailleurs("ntp.example.org", fuseau_posix_du_site(connecte))
    assert horloge(connecte, id_camera)["serveur_ntp"] == "ntp.example.org"
    depuis = tableau(connecte)[id_camera]["verifiee_le"]

    attendre_horloge(connecte, id_camera, lambda lue: lue["serveur_ntp"] == ADRESSE_TEMPS)
    ligne = attendre_ligne(connecte, id_camera, lambda ligne: ligne["verifiee_le"] != depuis)
    assert ligne["derive_s"] is not None
