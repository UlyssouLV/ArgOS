"""Page Enregistrement : débits, tenue vs Conservation, tableau des Caméras (sans interrupteur)."""

import re
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Page, expect

from stack_compose import client_du_site, compose
from test_connexion import se_connecter
from test_mac import cellule


def unique(prefixe: str) -> str:
    return f"{prefixe}-{uuid.uuid4().hex[:12]}"


def fuseau_du_site(api) -> ZoneInfo:
    return ZoneInfo(api.get("/api/heure-du-site").json()["fuseau"])


CONSERVATION_DEFAUT = 1
SEUIL_DEFAUT = 1_073_741_824


@pytest.fixture
def api(administrateur):
    with client_du_site() as client:
        assert client.post(
            "/api/session",
            json={"identifiant": administrateur["identifiant"], "mot_de_passe": administrateur["mot_de_passe"]},
        ).status_code == 204
        yield client
        assert client.patch(
            "/api/reglages-site",
            json={"conservation_h": CONSERVATION_DEFAUT, "seuil_octets_libres": SEUIL_DEFAUT},
        ).status_code == 200
        # Nettoyage des Caméras créées dans les tests de ce module.
        for camera in client.get("/api/cameras").json():
            if camera["nom"].startswith("Debit-"):
                client.patch(f"/api/cameras/{camera['id']}", json={"active": False, "enregistrement": False})
                client.delete(f"/api/cameras/{camera['id']}")


@pytest.fixture
def enregistrement(page: Page, administrateur) -> Page:
    page.goto("/enregistrement")
    se_connecter(page, **administrateur)
    expect(page.get_by_role("heading", name="Enregistrement")).to_be_visible()
    return page


def _ecrire_segment(id_camera: int, octets: int, nom_segment: str = "segment.mp4") -> None:
    compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from pathlib import Path; "
        f"p = Path('/enregistrements/camera-{id_camera}'); p.mkdir(parents=True, exist_ok=True); "
        f"(p / '{nom_segment}').write_bytes(b'x' * {octets})",
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


def test_agregats_et_tenue_visibles(enregistrement: Page, api):
    camera = api.post(
        "/api/cameras",
        json={"nom": unique("Debit"), "url_rtsp": f"rtsp://{unique('hote')}.invalid/flux"},
    ).json()
    assert api.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    libre = api.get("/api/espace-enregistrements").json()["libre_o"]
    debit_o_s = max(1000, libre // (2 * 3600))
    _fixer_debit_encodage(camera["id"], max(1, debit_o_s * 8 // 1000))

    enregistrement.reload()
    debit = enregistrement.get_by_role("region", name="Débit d’écriture")
    expect(debit.get_by_text("Débit (enregistrement en cours)", exact=True)).to_be_visible(timeout=10_000)
    expect(debit.get_by_text("Projection (toutes Caméras actives)", exact=True)).to_be_visible()
    conservation = enregistrement.get_by_role("region", name="Conservation", exact=True)
    expect(conservation).to_contain_text("Tenue estimée")
    expect(conservation).to_contain_text(re.compile(r"compatible avec la conservation|trop ambitieux|tenue inconnue"))


def test_la_tenue_avertit_quand_le_disque_ne_suit_pas(enregistrement: Page, api):
    """Débit d'encodage tel que le libre tient 2 h : 30 jours de Conservation sont trop ambitieux."""
    camera = api.post(
        "/api/cameras",
        json={"nom": unique("Debit"), "url_rtsp": f"rtsp://{unique('hote')}.invalid/flux"},
    ).json()
    assert api.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    libre = api.get("/api/espace-enregistrements").json()["libre_o"]
    _fixer_debit_encodage(camera["id"], max(1, libre // (2 * 3600) * 8 // 1000))
    assert api.patch("/api/reglages-site", json={"conservation_h": 30 * 24}).status_code == 200

    enregistrement.reload()
    conservation = enregistrement.get_by_role("region", name="Conservation", exact=True)
    expect(conservation.get_by_text("30 j", exact=True)).to_be_visible(timeout=10_000)
    expect(conservation.get_by_role("img", name="Avertissement").first).to_be_visible()
    expect(conservation).to_contain_text("trop ambitieux pour la conservation")


def test_resume_par_camera_nom_etat_debit_plus_ancien_segment(enregistrement: Page, api):
    nom = unique("Debit")
    camera = api.post(
        "/api/cameras",
        json={"nom": nom, "url_rtsp": f"rtsp://{unique('hote')}.invalid/flux"},
    ).json()
    assert api.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    _ecrire_segment(camera["id"], 150_000, nom_segment="2026-10-19_23-59-30-000000.mp4")

    enregistrement.reload()
    resume = enregistrement.get_by_role("table", name="Débits par Caméra")
    expect(resume).to_be_visible(timeout=10_000)
    ligne = resume.get_by_role("row").filter(has_text=nom)
    expect(cellule(resume, ligne, "État")).to_have_text(re.compile(r"enregistre|en erreur|à l'arrêt", re.I))
    expect(cellule(resume, ligne, "Débit")).to_contain_text(re.compile(r"o/s|Ko/s|Mo/s|inconnu"))
    plus_ancien = datetime(2026, 10, 19, 23, 59, 30, tzinfo=UTC)
    expect(cellule(resume, ligne, "Plus ancien Segment")).to_have_text(
        re.compile(rf"{plus_ancien.astimezone(fuseau_du_site(api)):%d/%m/%Y %H:%M}")
    )


def test_interrupteur_absent_de_la_page(enregistrement: Page):
    expect(enregistrement.get_by_role("switch", name="Enregistrement")).to_have_count(0)
