"""Finition de la 1.0.0 : focus visible au rouge de marque, même sur un contrôle natif sans style propre."""

from playwright.sync_api import Page, expect

from test_administration import administration, api, noms  # noqa: F401 (fixtures)
from test_heure_du_site import heure_du_site  # noqa: F401 (fixture)

ROUGE_DE_MARQUE = "rgb(200, 16, 46)"


def test_radio_native_focus_au_clavier_visible_au_rouge_de_marque(heure_du_site: Page):
    radio = heure_du_site.get_by_role("radio", name="Serveur NTP externe")
    expect(radio).to_be_enabled(timeout=10_000)
    heure_du_site.keyboard.press("Shift")  # dernière interaction au clavier : le focus qui suit est :focus-visible
    radio.focus()

    style = radio.evaluate(
        "e => { const s = getComputedStyle(e);"
        " return { visible: e.matches(':focus-visible'), style: s.outlineStyle, largeur: s.outlineWidth,"
        " couleur: s.outlineColor }; }"
    )

    assert style["visible"]
    assert style["style"] == "solid"
    assert float(style["largeur"].removesuffix("px")) >= 2
    assert style["couleur"] == ROUGE_DE_MARQUE
