"""Page Enregistrement : débits, tenue vs Conservation, résumé par Caméra (sans interrupteur)."""

import re
import uuid

import pytest
from playwright.sync_api import Page, expect

from stack_compose import client_du_site, compose
from test_connexion import se_connecter


def unique(prefixe: str) -> str:
    return f"{prefixe}-{uuid.uuid4().hex[:12]}"

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
    expect(enregistrement.get_by_role("heading", name="Enregistrement")).to_be_visible()
    expect(enregistrement.get_by_text("Débit (enregistrement en cours)", exact=True)).to_be_visible(timeout=10_000)
    expect(enregistrement.get_by_text("Projection (toutes Caméras actives)", exact=True)).to_be_visible()
    expect(enregistrement.locator(".tenue-ok, .tenue-ambitieuse, .tenue-inconnue").first).to_contain_text(
        re.compile(r"Tenue estimée")
    )
    expect(enregistrement.locator(".agregats-debit").first).to_contain_text(
        re.compile(r"compatible avec la conservation|trop ambitieux|tenue inconnue")
    )


def test_resume_par_camera_nom_etat_debit(enregistrement: Page, api):
    nom = unique("Debit")
    camera = api.post(
        "/api/cameras",
        json={"nom": nom, "url_rtsp": f"rtsp://{unique('hote')}.invalid/flux"},
    ).json()
    assert api.patch(f"/api/cameras/{camera['id']}", json={"enregistrement": True}).status_code == 200
    _ecrire_segment(camera["id"], 150_000)

    enregistrement.reload()
    resume = enregistrement.get_by_role("table", name="Débits par Caméra")
    expect(resume).to_be_visible(timeout=10_000)
    ligne = resume.get_by_role("row").filter(has_text=nom)
    expect(ligne).to_contain_text(re.compile(r"enregistre|en erreur|à l'arrêt", re.I))
    expect(ligne).to_contain_text(re.compile(r"o/s|Ko/s|Mo/s|inconnu"))


def test_interrupteur_absent_de_la_page(enregistrement: Page):
    expect(enregistrement.get_by_role("switch", name="Enregistrement")).to_have_count(0)
