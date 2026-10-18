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


def _ecrire_segment(id_camera: int, octets: int) -> None:
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from pathlib import Path; "
        f"p = Path('/enregistrements/camera-{id_camera}'); p.mkdir(parents=True, exist_ok=True); "
        f"(p / 'segment.mp4').write_bytes(b'x' * {octets})",
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
    octets = 150_000  # → 500 o/s sur 300 s
    _ecrire_segment(camera["id"], octets)

    corps = connecte.get("/api/debits-ecriture").json()

    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["source_debit"] == "mesure"
    assert resume["debit_o_s"] == octets // FENETRE_MESURE_S


def test_repli_encodage_sans_segments(connecte, creer_camera):
    camera = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    _fixer_debit_encodage(camera["id"], 4096)  # kbit/s → 512_000 o/s

    corps = connecte.get("/api/debits-ecriture").json()

    resume = next(c for c in corps["cameras"] if c["id"] == camera["id"])
    assert resume["source_debit"] == "encodage"
    assert resume["debit_o_s"] == 4096 * 1000 // 8


def test_agregats_enregistrement_et_projection(connecte, creer_camera):
    a = creer_camera().json()
    b = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{a['id']}", json={"enregistrement": True}).status_code == 200
    # b active mais enregistrement OFF
    _ecrire_segment(a["id"], 300_000)  # 1000 o/s
    _fixer_debit_encodage(b["id"], 8)  # 1000 o/s

    corps = connecte.get("/api/debits-ecriture").json()
    par_id = {c["id"]: c for c in corps["cameras"]}

    assert par_id[a["id"]]["debit_o_s"] == 1000
    assert par_id[a["id"]]["source_debit"] == "mesure"
    assert par_id[b["id"]]["debit_o_s"] == 1000
    assert par_id[b["id"]]["source_debit"] == "encodage"

    en_cours = [c for c in corps["cameras"] if c["enregistrement"]]
    actives = [c for c in corps["cameras"] if c["active"]]
    if all(c["source_debit"] != "inconnu" for c in en_cours):
        assert corps["debit_enregistrement_o_s"] == sum(c["debit_o_s"] for c in en_cours)
    if all(c["source_debit"] != "inconnu" for c in actives):
        assert corps["debit_projection_o_s"] == sum(c["debit_o_s"] for c in actives)
    # Au moins nos deux Caméras : a dans l'enregistrement, a+b dans la projection.
    assert a["id"] in {c["id"] for c in en_cours}
    assert {a["id"], b["id"]} <= {c["id"] for c in actives}


def test_agregat_inconnu_si_une_camera_du_jeu_est_inconnue(connecte, creer_camera):
    a = creer_camera().json()
    b = creer_camera().json()
    assert connecte.patch(f"/api/cameras/{a['id']}", json={"enregistrement": True}).status_code == 200
    assert connecte.patch(f"/api/cameras/{b['id']}", json={"enregistrement": True}).status_code == 200
    _ecrire_segment(a["id"], 300_000)
    # b : pas de segments ni encodage → inconnu

    corps = connecte.get("/api/debits-ecriture").json()
    par_id = {c["id"]: c for c in corps["cameras"]}

    assert par_id[b["id"]]["source_debit"] == "inconnu"
    assert corps["debit_enregistrement_o_s"] is None
    assert corps["debit_projection_o_s"] is None


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
    assert corps["tenue_enregistrement_s"] == pytest.approx(libre / debit_o_s, rel=0.05)
    assert corps["tenue_enregistrement_ok"] is True


def test_tenue_trop_ambitieuse_quand_conservation_depasse(connecte, creer_camera):
    assert connecte.patch("/api/reglages-site", json={"conservation_h": 24}).status_code == 200
    camera = creer_camera().json()
    _seul_enregistrement(connecte, camera["id"])
    libre = connecte.get("/api/espace-enregistrements").json()["libre_o"]
    # Débit encodage tel que la tenue ≈ 1 h (< conservation 24 h)
    debit_o_s = max(1000, libre // 3600)
    kbit_s = max(1, debit_o_s * 8 // 1000)
    debit_o_s = kbit_s * 1000 // 8
    _fixer_debit_encodage(camera["id"], kbit_s)

    corps = connecte.get("/api/debits-ecriture").json()

    assert corps["conservation_s"] == 24 * 3600
    assert corps["debit_enregistrement_o_s"] == debit_o_s
    assert corps["tenue_enregistrement_ok"] is False
