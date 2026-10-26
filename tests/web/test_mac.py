"""MAC des Appareils dans l'Administration (Caméras, Candidats, Aperçu), de bout en bout dans Chromium.

Les Caméras simulées ont des MAC fixes (compose.simulation.yaml). Une MAC inconnue (réseau routé) ne se
produit pas dans la stack : la réponse de l'API est retouchée pour la retirer.
"""

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from stack_compose import MACS_SIMULEES, adresses_ip
from test_administration import administration, api, creer, ligne, noms, url_injoignable  # noqa: F401 (fixtures)
from test_ajout_camera import DELAI_APERCU_MS, ajouter_par_ip, sans_essai  # noqa: F401 (fixtures)
from test_detection import candidats, ouvrir_detection, tableau

INCONNUE = "—"


def ip_de(numero: int) -> str:
    (ip,) = adresses_ip(f"camera-simulee-{numero}")
    return ip


def cellule(tableau: Locator, rangee: Locator, colonne: str) -> Locator:
    expect(tableau.get_by_role("columnheader", name=colonne, exact=True)).to_be_visible()
    entetes = tableau.get_by_role("columnheader").all_inner_texts()
    return rangee.get_by_role("cell").nth(entetes.index(colonne))


def sans_mac(page: Page, chemin: str, ip: str) -> None:
    """La réponse de l'API à `POST chemin` perd la MAC de `ip`, comme derrière un routeur."""

    def retirer(route: Route) -> None:
        reponse = route.fetch()
        corps = reponse.json()
        if "candidats" in corps:
            corps["candidats"] = [c | {"mac": None} if c["ip"] == ip else c for c in corps["candidats"]]
        else:
            corps["mac"] = None
        route.fulfill(response=reponse, json=corps)

    page.route(f"**{chemin}", lambda route: retirer(route) if route.request.method == "POST" else route.continue_())


def test_colonne_mac_des_cameras(administration: Page, api, noms, sans_essai):
    lue, inconnue = noms("Lue"), noms("Inconnue")
    assert api.post("/api/essai", json={"ip": ip_de(1), "port": 554}, timeout=30).json()["issue"] == "flux_trouve"
    assert api.post("/api/essai/camera", json={"nom": lue}).status_code == 201
    creer(administration, api, inconnue, url_injoignable(), emplacement="Portail")
    tableau = administration.get_by_role("table", name="Caméras", exact=True)

    expect(cellule(tableau, ligne(administration, lue), "Adresse")).to_contain_text(f"MAC {MACS_SIMULEES[1]}")
    expect(cellule(tableau, ligne(administration, inconnue), "Adresse")).to_contain_text(f"MAC {INCONNUE}")


@pytest.mark.parametrize("tableau_candidats", ["Candidats", "Déjà configurées"])
def test_colonne_mac_des_candidats(administration: Page, api, noms, tableau_candidats):
    if tableau_candidats == "Déjà configurées":
        assert api.post("/api/essai", json={"ip": ip_de(1), "port": 554}, timeout=30).json()["issue"] == "flux_trouve"
        assert api.post("/api/essai/camera", json={"nom": noms()}).status_code == 201
    sans_mac(administration, "/api/detection", ip_de(3))

    boite = ouvrir_detection(administration)

    nouveaux = candidats(boite)
    if tableau_candidats == "Déjà configurées":
        deja = tableau(boite, "Déjà configurées")
        expect(cellule(deja, deja.get_by_role("row").filter(has_text=ip_de(1)), "MAC")).to_have_text(MACS_SIMULEES[1])
    else:
        expect(cellule(nouveaux, nouveaux.get_by_role("row").filter(has_text=ip_de(2)), "MAC")).to_have_text(
            MACS_SIMULEES[2]
        )
        expect(cellule(nouveaux, nouveaux.get_by_role("row").filter(has_text=ip_de(3)), "MAC")).to_have_text(
            INCONNUE
        )


@pytest.mark.parametrize("lisible", [True, False])
def test_mac_dans_l_apercu(administration: Page, sans_essai, lisible):
    ip = ip_de(1)
    if not lisible:
        sans_mac(administration, "/api/essai", ip)

    ajouter_par_ip(administration, ip)

    panneau = administration.get_by_role("form", name=f"Ajouter {ip}:554")
    expect(panneau.locator("video")).to_be_visible(timeout=DELAI_APERCU_MS)
    expect(panneau.get_by_text("MAC de l'Appareil")).to_have_text(
        f"MAC de l'Appareil : {MACS_SIMULEES[1] if lisible else INCONNUE}"
    )
