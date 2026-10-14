"""Réglages de la Caméra, lus par ONVIF sur les Caméras simulées (simulation/onvif/), vus de l'extérieur de la stack.

La 2 répond sur `8899` avec ses identifiants de dev, la 4 sur `80` sans identifiants, les 1 et 3 pas du tout.
Les simulateurs ONVIF sont recréés « sortie d'usine » au début du module et après chaque test qui les change.
"""

from datetime import UTC, datetime

import pytest

from stack_compose import (
    camera_simulee_4_sans_recreation_de_la_date,
    compose,
    regler_camera_simulee_4_en_onvif,
    remettre_onvif_en_usine,
    url_camera_simulee,
)
from test_cameras import connecte, creer_camera, unique  # noqa: F401 (fixtures)
from test_essai import IP_SANS_CAMERA

# La sonde de chaque port, puis la lecture : délais courts, mais une caméra éteinte se fait attendre.
DELAI_LECTURE_S = 30
VINGT_CINQ_ANS_S = 25 * 365 * 24 * 3600

USINE_INCRUSTATIONS = {
    "nom": {"affichee": True, "texte": "CAM01", "position": "UpperLeft", "peut_etre_reaffichee": True},
    "date_heure": {
        "affichee": True,
        "format": "yyyy-MM-dd HH:mm:ss",
        "position": "LowerLeft",
        "peut_etre_reaffichee": True,
    },
}


# Incrustation du nom de camera-simulee-4 (`OSD_1`), placée par la caméra hors des quatre coins.
OSD_NOM_PERSONNALISE = (
    '<trt:SetOSD><trt:OSD token="OSD_1"><tt:VideoSourceConfigurationToken>VideoSourceConfig_1'
    "</tt:VideoSourceConfigurationToken><tt:Type>Text</tt:Type>"
    '<tt:Position><tt:Type>Custom</tt:Type><tt:Pos x="0.2" y="-0.5"/></tt:Position>'
    "<tt:TextString><tt:Type>Plain</tt:Type><tt:PlainText>CAM01</tt:PlainText></tt:TextString>"
    "</trt:OSD></trt:SetOSD>"
)


@pytest.fixture(scope="module", autouse=True)
def usine():
    remettre_onvif_en_usine()


@pytest.fixture
def camera_simulee(creer_camera):
    """Crée une Caméra sur une Caméra simulée ; `identifiants` remplace ceux de l'URL (`user:mdp`, ou `""`)."""

    def _creer(numero: int, identifiants: str | None = None) -> int:
        url = url_camera_simulee(numero, unique("reglages"), identifiants=identifiants is None)
        if identifiants:
            url = url.replace("rtsp://", f"rtsp://{identifiants}@")
        reponse = creer_camera(url_rtsp=url)
        assert reponse.status_code == 201
        return reponse.json()["id"]

    return _creer


def lire(client, id_camera: int):
    return client.get(f"/api/cameras/{id_camera}/reglages", timeout=DELAI_LECTURE_S)


def port_onvif(client, id_camera: int) -> int | None:
    return client.get(f"/api/cameras/{id_camera}").json()["port_onvif"]


def assert_usine(reglages: dict) -> None:
    horloge = reglages["horloge"]
    assert horloge["date_heure_utc"].startswith("1999-12-31T")
    assert horloge["ecart_s"] < -VINGT_CINQ_ANS_S
    assert {cle: horloge[cle] for cle in ("fuseau_posix", "fuseau", "mode", "serveur_ntp")} == {
        "fuseau_posix": "AWST-8",
        "fuseau": None,
        "mode": "manuel",
        "serveur_ntp": "NTP",
    }
    assert reglages["incrustations"] == USINE_INCRUSTATIONS


def test_reglages_sans_session_401(client):
    assert client.get("/api/cameras/1/reglages").status_code == 401


def test_camera_simulee_2_usine_sur_le_port_8899_retenu(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    assert port_onvif(connecte, id_camera) is None

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert_usine(reponse.json())
    assert port_onvif(connecte, id_camera) == 8899


def test_camera_simulee_4_sans_identifiants_usine_sur_le_port_80(connecte, camera_simulee):
    id_camera = camera_simulee(4)

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert_usine(reponse.json())
    assert port_onvif(connecte, id_camera) == 80


def test_ecart_avec_l_heure_du_site(connecte, camera_simulee):
    avant = datetime.now(UTC)

    horloge = lire(connecte, camera_simulee(4)).json()["horloge"]

    camera = datetime.fromisoformat(horloge["date_heure_utc"])
    assert abs(horloge["ecart_s"] - (camera - avant).total_seconds()) < 60


def test_port_retenu_qui_ne_repond_plus_nouvelle_recherche(connecte, camera_simulee):
    id_camera = camera_simulee(2)
    # Aucune Caméra simulée ne répond en ONVIF sur 2000 : comme une caméra dont le port a changé.
    compose("exec", "-T", "db", "psql", "-U", "argos", "-d", "argos", "-c",
            f"UPDATE cameras SET port_onvif = 2000 WHERE id = {id_camera}")
    assert port_onvif(connecte, id_camera) == 2000

    reponse = lire(connecte, id_camera)

    assert reponse.status_code == 200
    assert port_onvif(connecte, id_camera) == 8899


@pytest.mark.parametrize("numero", [1, 3])
def test_cameras_simulees_1_et_3_sans_onvif(connecte, camera_simulee, numero):
    reponse = lire(connecte, camera_simulee(numero))

    assert reponse.status_code == 502
    assert reponse.json() == {"code": "sans_onvif", "detail": "Cette caméra ne répond pas en ONVIF."}


@pytest.mark.parametrize("identifiants", ["admin:mauvais", ""])
def test_mauvais_identifiants_ou_aucun_refuses(connecte, camera_simulee, identifiants):
    reponse = lire(connecte, camera_simulee(2, identifiants=identifiants))

    assert reponse.status_code == 502
    assert reponse.json() == {
        "code": "identifiants_refuses",
        "detail": "La caméra refuse ces identifiants en ONVIF.",
    }


def test_camera_eteinte_injoignable(connecte, creer_camera):
    reponse = creer_camera(url_rtsp=f"rtsp://{IP_SANS_CAMERA}/{unique('eteinte')}")
    assert reponse.status_code == 201

    reponse = lire(connecte, reponse.json()["id"])

    assert reponse.status_code == 502
    assert reponse.json() == {"code": "injoignable", "detail": "Caméra injoignable."}


def test_camera_desactivee_404(connecte, camera_simulee):
    id_camera = camera_simulee(4)
    assert connecte.patch(f"/api/cameras/{id_camera}", json={"active": False}).status_code == 200

    assert lire(connecte, id_camera).status_code == 404


def test_camera_inconnue_404(connecte):
    assert lire(connecte, 999_999_999).status_code == 404


def test_url_modifiee_oublie_le_port_retenu(connecte, camera_simulee):
    id_camera = camera_simulee(4)
    assert lire(connecte, id_camera).status_code == 200

    url = url_camera_simulee(2, unique("reglages"))
    assert connecte.patch(f"/api/cameras/{id_camera}", json={"url_rtsp": url}).status_code == 200

    assert port_onvif(connecte, id_camera) is None


@pytest.fixture
def regler_fuseau():
    """Règle le fuseau de camera-simulee-4 (heure d'usine gardée) ; la remet « sortie d'usine » ensuite."""

    def _regler(fuseau: str) -> None:
        regler_camera_simulee_4_en_onvif(
            "device",
            "<tds:SetSystemDateAndTime><tds:DateTimeType>Manual</tds:DateTimeType>"
            "<tds:DaylightSavings>false</tds:DaylightSavings>"
            f"<tds:TimeZone><tt:TZ>{fuseau}</tt:TZ></tds:TimeZone><tds:UTCDateTime>"
            "<tt:Date><tt:Year>1999</tt:Year><tt:Month>12</tt:Month><tt:Day>31</tt:Day></tt:Date>"
            "<tt:Time><tt:Hour>0</tt:Hour><tt:Minute>0</tt:Minute><tt:Second>0</tt:Second></tt:Time>"
            "</tds:UTCDateTime></tds:SetSystemDateAndTime>",
        )

    yield _regler
    remettre_onvif_en_usine()


@pytest.fixture
def placer_le_nom_hors_d_un_coin():
    """Place l'Incrustation du nom de camera-simulee-4 hors d'un coin ; la remet « sortie d'usine » ensuite."""
    yield lambda: regler_camera_simulee_4_en_onvif("media", OSD_NOM_PERSONNALISE)
    remettre_onvif_en_usine()


def test_fuseau_posix_reconnu_rendu_en_nom_iana(connecte, camera_simulee, regler_fuseau):
    regler_fuseau("CET-1CEST,M3.5.0,M10.5.0/3")

    horloge = lire(connecte, camera_simulee(4)).json()["horloge"]

    assert horloge["fuseau_posix"] == "CET-1CEST,M3.5.0,M10.5.0/3"
    assert horloge["fuseau"] == "Europe/Paris"



def test_incrustation_hors_d_un_coin_en_position_personnalisee(connecte, camera_simulee, placer_le_nom_hors_d_un_coin):
    placer_le_nom_hors_d_un_coin()

    nom = lire(connecte, camera_simulee(4)).json()["incrustations"]["nom"]

    assert nom["position"] == "Custom"


# --- Modifier les Réglages ---------------------------------------------------------------------------------------


@pytest.fixture
def remise_en_usine():
    """Les tests qui modifient une caméra la remettent « sortie d'usine » ensuite."""
    yield
    remettre_onvif_en_usine()


def modifier(client, id_camera: int, incrustations: dict):
    return client.patch(
        f"/api/cameras/{id_camera}/reglages", json={"incrustations": incrustations}, timeout=DELAI_LECTURE_S
    )


def champs(reponse) -> dict[str, dict]:
    """Résultat par champ envoyé (`incrustations.nom.texte`…), sans la clé `champ`."""
    assert reponse.status_code == 200, reponse.text
    return {c.pop("champ"): c for c in reponse.json()["champs"]}


def test_modifier_sans_session_401(client):
    assert client.patch("/api/cameras/1/reglages", json={}).status_code == 401


def test_texte_du_nom_pris_et_confirme_par_une_nouvelle_lecture(connecte, camera_simulee, remise_en_usine):
    id_camera = camera_simulee(2)

    reponse = modifier(connecte, id_camera, {"nom": {"texte": "Entrée"}})

    assert champs(reponse) == {
        "incrustations.nom.texte": {"demande": "Entrée", "relu": "Entrée", "statut": "pris"}
    }
    assert reponse.json()["reglages"]["incrustations"]["nom"]["texte"] == "Entrée"
    nom = lire(connecte, id_camera).json()["incrustations"]["nom"]
    assert (nom["texte"], nom["position"]) == ("Entrée", "UpperLeft")


def test_coin_de_chaque_incrustation_pris(connecte, camera_simulee, remise_en_usine):
    id_camera = camera_simulee(4)

    reponse = modifier(
        connecte, id_camera, {"nom": {"position": "LowerRight"}, "date_heure": {"position": "UpperRight"}}
    )

    assert champs(reponse) == {
        "incrustations.nom.position": {"demande": "LowerRight", "relu": "LowerRight", "statut": "pris"},
        "incrustations.date_heure.position": {"demande": "UpperRight", "relu": "UpperRight", "statut": "pris"},
    }
    incrustations = lire(connecte, id_camera).json()["incrustations"]
    assert incrustations["nom"]["texte"] == "CAM01"
    assert incrustations["date_heure"]["format"] == "yyyy-MM-dd HH:mm:ss"


def test_position_personnalisee_remise_dans_un_coin(
    connecte, camera_simulee, placer_le_nom_hors_d_un_coin, remise_en_usine
):
    placer_le_nom_hors_d_un_coin()

    reponse = modifier(connecte, camera_simulee(4), {"nom": {"position": "UpperRight"}})

    assert champs(reponse)["incrustations.nom.position"] == {
        "demande": "UpperRight",
        "relu": "UpperRight",
        "statut": "pris",
    }


@pytest.mark.parametrize("incrustation", ["nom", "date_heure"])
def test_incrustation_cachee_puis_reaffichee(connecte, camera_simulee, remise_en_usine, incrustation):
    id_camera = camera_simulee(2)

    cachee = modifier(connecte, id_camera, {incrustation: {"affichee": False}})

    assert champs(cachee) == {
        f"incrustations.{incrustation}.affichee": {"demande": False, "relu": False, "statut": "pris"}
    }
    assert lire(connecte, id_camera).json()["incrustations"][incrustation]["affichee"] is False

    reaffichee = modifier(connecte, id_camera, {incrustation: {"affichee": True}})

    assert champs(reaffichee) == {
        f"incrustations.{incrustation}.affichee": {"demande": True, "relu": True, "statut": "pris"}
    }
    assert lire(connecte, id_camera).json()["incrustations"][incrustation]["affichee"] is True


def test_nom_reaffiche_avec_son_texte_et_son_coin(connecte, camera_simulee, remise_en_usine):
    id_camera = camera_simulee(4)
    modifier(connecte, id_camera, {"nom": {"affichee": False}})

    reponse = modifier(connecte, id_camera, {"nom": {"affichee": True, "texte": "Portail", "position": "LowerRight"}})

    assert {champ: c["statut"] for champ, c in champs(reponse).items()} == {
        "incrustations.nom.affichee": "pris",
        "incrustations.nom.texte": "pris",
        "incrustations.nom.position": "pris",
    }
    nom = lire(connecte, id_camera).json()["incrustations"]["nom"]
    assert (nom["affichee"], nom["texte"], nom["position"]) == (True, "Portail", "LowerRight")


@pytest.fixture
def sans_recreation_de_la_date():
    camera_simulee_4_sans_recreation_de_la_date()
    yield
    remettre_onvif_en_usine()


def test_afficher_refuse_sans_appel_si_la_camera_n_annonce_pas_la_creation(
    connecte, camera_simulee, sans_recreation_de_la_date
):
    id_camera = camera_simulee(4)
    date_heure = lire(connecte, id_camera).json()["incrustations"]["date_heure"]
    assert date_heure["peut_etre_reaffichee"] is False
    assert champs(modifier(connecte, id_camera, {"date_heure": {"affichee": False}}))[
        "incrustations.date_heure.affichee"
    ]["statut"] == "pris"

    reponse = modifier(connecte, id_camera, {"date_heure": {"affichee": True, "position": "UpperRight"}})

    assert champs(reponse) == {
        "incrustations.date_heure.affichee": {"demande": True, "relu": False, "statut": "refuse"},
        "incrustations.date_heure.position": {"demande": "UpperRight", "relu": None, "statut": "refuse"},
    }


def test_champ_refuse_par_la_camera_n_empeche_pas_les_autres(connecte, camera_simulee, remise_en_usine):
    id_camera = camera_simulee(2)
    # La Caméra simulée refuse un texte de plus de 32 caractères (simulation/onvif/README.md).
    trop_long = "X" * 33

    reponse = modifier(
        connecte,
        id_camera,
        {"nom": {"texte": trop_long, "position": "UpperRight"}, "date_heure": {"position": "LowerRight"}},
    )

    assert champs(reponse) == {
        "incrustations.nom.texte": {"demande": trop_long, "relu": "CAM01", "statut": "refuse"},
        "incrustations.nom.position": {"demande": "UpperRight", "relu": "UpperRight", "statut": "pris"},
        "incrustations.date_heure.position": {"demande": "LowerRight", "relu": "LowerRight", "statut": "pris"},
    }


def test_cacher_avec_d_autres_champs_de_la_meme_incrustation_422(connecte, camera_simulee):
    reponse = modifier(connecte, camera_simulee(4), {"nom": {"affichee": False, "texte": "Entrée"}})

    assert reponse.status_code == 422


@pytest.mark.parametrize(
    "incrustations",
    [{"nom": {"position": "Custom"}}, {"date_heure": {"texte": "x"}}, {"date_heure": {"format": "dd/MM/yyyy"}}],
    ids=["position_personnalisee", "texte_de_la_date", "format_de_la_date"],
)
def test_champs_non_reglables_422(connecte, camera_simulee, incrustations):
    assert modifier(connecte, camera_simulee(4), incrustations).status_code == 422


def test_modifier_camera_desactivee_404(connecte, camera_simulee):
    id_camera = camera_simulee(4)
    assert connecte.patch(f"/api/cameras/{id_camera}", json={"active": False}).status_code == 200

    assert modifier(connecte, id_camera, {"nom": {"texte": "Entrée"}}).status_code == 404


def test_modifier_camera_sans_onvif_502(connecte, camera_simulee):
    reponse = modifier(connecte, camera_simulee(1), {"nom": {"texte": "Entrée"}})

    assert reponse.status_code == 502
    assert reponse.json()["code"] == "sans_onvif"
