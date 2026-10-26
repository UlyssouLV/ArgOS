"""Débits d'écriture : mesure sur segments, repli encodage, agrégats et tenue vs Conservation."""

import pytest

from stack_compose import client_du_site, compose
from test_cameras import connecte, creer_camera  # noqa: F401

CONSERVATION_DEFAUT = 1
SEUIL_DEFAUT = 1_073_741_824
# Aligné sur la fenêtre de mesure côté API (segments récents).
FENETRE_MESURE_S = 300


@pytest.fixture(autouse=True)
def reglages_remis(administrateur):
    def remettre() -> None:
        with client_du_site() as c:
            assert c.post(
                "/api/session",
                json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
            ).status_code == 204
            assert c.patch(
                "/api/reglages-site",
                json={"conservation_h": CONSERVATION_DEFAUT, "seuil_octets_libres": SEUIL_DEFAUT},
            ).status_code == 200

    remettre()
    yield
    remettre()


def _ecrire_segment(id_camera: int, octets: int, age_s: int = 250) -> None:
    """Écrit un segment daté de `age_s` s (dans la fenêtre) ; débit attendu ≈ octets // age_s."""
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "import time\n"
        "from pathlib import Path\n"
        f"p = Path('/enregistrements/camera-{id_camera}'); p.mkdir(parents=True, exist_ok=True)\n"
        f"f = p / 'segment.mp4'; f.write_bytes(b'x' * {octets})\n"
        f"t = time.time() - {age_s}; __import__('os').utime(f, (t, t))\n",
    )


def _fixer_debit_encodage(id_camera: int, kbit_s: int) -> None:
    script = (
        "import os\n"
        "from sqlalchemy import create_engine, text\n"
        "e = create_engine(os.environ['ARGOS_URL_BASE'])\n"
        "with e.begin() as c:\n"
        "    c.execute(\n"
        "        text('UPDATE cameras SET debit_encodage_kbit_s = :d WHERE id = :i'),\n"
        f"        {{'d': {kbit_s}, 'i': {id_camera}}},\n"
        "    )\n"
    )
    compose("exec", "-T", "api", "python", "-c", script)


def _seul_enregistrement(connecte, id_camera: int) -> None:
    """Coupe l'enregistrement des autres Caméras pour des assertions de tenue stables."""
    for camera in connecte.get("/api/cameras").json():
        voulu = camera["id"] == id_camera
        if camera["enregistrement"] != voulu:
            assert (
                connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": voulu}).status_code == 200
            )


def test_debits_sans_session_401(client):
    assert client.get("/api/debits-ecriture").status_code == 401


def test_camera_sans_segments_ni_encodage_inconnu(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200

    corps = connecte.get("/api/debits-ecriture").json()

    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["nom"] == camera["nom"]
    assert resume["enregistrement"] is True
    assert resume["debit_o_s"] is None
    assert resume["source_debit"] == "inconnu"


def test_debit_mesure_sur_segments_recents(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    age_s = 250
    octets = 150_000  # → 600 o/s sur 250 s
    _ecrire_segment(camera["id"], octets, age_s=age_s)

    corps = connecte.get("/api/debits-ecriture").json()

    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["source_debit"] == "mesure"
    # rel large : entre utime (compose exec) et le GET, l'âge réel dérive de plusieurs secondes en CI.
    assert resume["debit_o_s"] == pytest.approx(octets / age_s, rel=0.2)


def test_debit_mesure_fenetre_courte_si_segments_recents(connecte, creer_camera):
    """Un enregistrement tout juste démarré ne divise pas par la fenêtre pleine (sous-estimation)."""
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    # 30 s : avec 10 s, un retard compose de 2–3 s sortait déjà du rel=0.15.
    age_s = 30
    octets = 50_000
    _ecrire_segment(camera["id"], octets, age_s=age_s)

    corps = connecte.get("/api/debits-ecriture").json()

    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["source_debit"] == "mesure"
    assert resume["debit_o_s"] == pytest.approx(octets / age_s, rel=0.25)
    assert resume["debit_o_s"] > octets // FENETRE_MESURE_S


def test_repli_encodage_sans_segments(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    _fixer_debit_encodage(camera["id"], 4096)  # kbit/s → 512_000 o/s

    corps = connecte.get("/api/debits-ecriture").json()

    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["source_debit"] == "encodage"
    assert resume["debit_o_s"] == 4096 * 1000 // 8


def test_enregistrement_on_ne_bloque_pas_si_repli_onvif_impossible(connecte, creer_camera):
    """Allumer l'enregistrement reste 200 même si le peuplement ONVIF du repli échoue (hôte .invalid)."""
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    resume = next(c for c in connecte.get("/api/debits-ecriture").json()["cameras"] if c["id"] == camera["id"])
    assert resume["enregistrement"] is True
    assert resume["source_debit"] == "inconnu"


def test_agregats_enregistrement_et_projection(connecte, creer_camera):
    a = creer_camera().json()
    b = creer_camera().json()
    _seul_enregistrement(connecte, a["id"])
    # b active mais enregistrement OFF
    age_s = 250
    _ecrire_segment(a["id"], 250_000, age_s=age_s)  # ≈ 1000 o/s
    _fixer_debit_encodage(b["id"], 8)  # 1000 o/s

    corps = connecte.get("/api/debits-ecriture").json()
    par_id = {c["id"]: c for c in corps["cameras"]}

    assert par_id[a["id"]]["debit_o_s"] == pytest.approx(250_000 / age_s, rel=0.2)
    assert par_id[a["id"]]["source_debit"] == "mesure"
    assert par_id[b["id"]]["debit_o_s"] == 1000
    assert par_id[b["id"]]["source_debit"] == "encodage"

    en_cours = [c for c in corps["cameras"] if c["enregistrement"]]
    actives = [c for c in corps["cameras"] if c["active"]]
    # Ne somment que nos Caméras : d'autres enregistrements résiduels cassent une somme globale stricte.
    nos_en_cours = [c for c in en_cours if c["id"] in {a["id"], b["id"]}]
    nos_actives = [c for c in actives if c["id"] in {a["id"], b["id"]}]
    assert sum(c["debit_o_s"] or 0 for c in nos_en_cours if c["source_debit"] != "inconnu") == pytest.approx(
        par_id[a["id"]]["debit_o_s"], rel=0.2
    )
    assert {c["id"] for c in nos_actives} == {a["id"], b["id"]}
    assert a["id"] in {c["id"] for c in en_cours}
    assert {a["id"], b["id"]} <= {c["id"] for c in actives}


def test_agregat_somme_les_connus_si_une_camera_est_inconnue(connecte, creer_camera):
    a = creer_camera().json()
    b = creer_camera().json()
    _seul_enregistrement(connecte, a["id"])
    assert connecte.patch(f"/api/cameras/{b['id']}", json={"enregistrement": True}).status_code == 200
    age_s = 250
    _ecrire_segment(a["id"], 250_000, age_s=age_s)  # ≈ 1000 o/s
    # b : hôte .invalid → pas de repli ONVIF ; sans segments → inconnu

    corps = connecte.get("/api/debits-ecriture").json()
    par_id = {c["id"]: c for c in corps["cameras"]}

    assert par_id[a["id"]]["source_debit"] == "mesure"
    debit_a = par_id[a["id"]]["debit_o_s"]
    assert debit_a == pytest.approx(250_000 / age_s, rel=0.2)
    assert par_id[b["id"]]["source_debit"] == "inconnu"
    # Seules a (mesure) et b (inconnu) enregistrent : agrégat = débit de a.
    assert corps["debit_enregistrement_o_s"] == debit_a


def test_agregat_none_si_toutes_inconnues(connecte, creer_camera):
    camera = creer_camera().json()
    _seul_enregistrement(connecte, camera["id"])
    # Hôte .invalid : pas de repli ONVIF ; sans segments → inconnu.
    corps = connecte.get("/api/debits-ecriture").json()
    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["source_debit"] == "inconnu"
    assert corps["debit_enregistrement_o_s"] is None


def test_tenue_confrontée_a_la_conservation(connecte, creer_camera):
    camera = creer_camera().json()
    _seul_enregistrement(connecte, camera["id"])
    libre = connecte.get("/api/espace-enregistrements").json()["libre_o"]
    # Débit encodage tel que la tenue ≈ 2 h (> conservation 1 h) → OK
    debit_o_s = max(1000, libre // (2 * 3600))
    kbit_s = max(1, debit_o_s * 8 // 1000)
    debit_o_s = kbit_s * 1000 // 8
    _fixer_debit_encodage(camera["id"], kbit_s)

    corps = connecte.get("/api/debits-ecriture").json()

    assert corps["conservation_s"] == CONSERVATION_DEFAUT * 3600
    assert corps["debit_enregistrement_o_s"] == debit_o_s
    assert corps["tenue_enregistrement_s"] is not None
    assert corps["tenue_enregistrement_s"] == pytest.approx(libre / debit_o_s, rel=0.2)
    assert corps["tenue_enregistrement_ok"] is True
    assert corps["tenue_enregistrement_s"] >= corps["conservation_s"]


def test_tenue_trop_ambitieuse_quand_conservation_depasse(connecte, creer_camera):
    assert connecte.patch("/api/reglages-site", json={"conservation_h": 24}).status_code == 200
    camera = creer_camera().json()
    _seul_enregistrement(connecte, camera["id"])
    libre = connecte.get("/api/espace-enregistrements").json()["libre_o"]
    # Débit encodage tel que la tenue ≈ 1 h (< conservation 24 h) — marge : viser ~0,5 h.
    debit_o_s = max(1000, libre // 1800)
    kbit_s = max(1, debit_o_s * 8 // 1000)
    debit_o_s = kbit_s * 1000 // 8
    _fixer_debit_encodage(camera["id"], kbit_s)

    corps = connecte.get("/api/debits-ecriture").json()

    assert corps["conservation_s"] == 24 * 3600
    assert corps["debit_enregistrement_o_s"] == debit_o_s
    assert corps["tenue_enregistrement_ok"] is False
    assert corps["tenue_enregistrement_s"] is not None
    assert corps["tenue_enregistrement_s"] < corps["conservation_s"]


def test_plus_ancien_segment_de_chaque_camera(connecte, creer_camera):
    """Début du plus ancien Segment, lu dans son nom (recordPath du pont, heure UTC) ; aucun : `None`."""
    avec = creer_camera().json()
    sans = creer_camera().json()
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from pathlib import Path\n"
        f"p = Path('/enregistrements/camera-{avec['id']}'); p.mkdir(parents=True, exist_ok=True)\n"
        "(p / '2026-10-20_08-15-00-000000.mp4').write_bytes(b'x')\n"
        "(p / '2026-10-19_23-59-30-500000.mp4').write_bytes(b'x')\n"
        "(p / 'pas-un-segment.mp4').write_bytes(b'x')\n",
    )

    cameras = {c["id"]: c for c in connecte.get("/api/debits-ecriture").json()["cameras"]}

    assert cameras[avec["id"]]["plus_ancien_segment"] == "2026-10-19T23:59:30.500000Z"
    assert cameras[sans["id"]]["plus_ancien_segment"] is None
