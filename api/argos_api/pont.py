"""MediaMTX en pont (docs/adr/0001-mediamtx-en-pont.md) : chaque Caméra active relayée par un chemin `camera-<id>`.

Réconciliation : les Caméras actives voulues en entrée, les chemins `camera-*` de MediaMTX ajustés
(ajoutés, source mise à jour, retirés) par son API de contrôle. Les autres chemins ne sont jamais
touchés. Une erreur sur un chemin n'empêche pas les autres : le tour suivant rattrape.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping

journal = logging.getLogger(__name__)

PREFIXE = "camera-"
CHEMINS_PAR_PAGE = 100


def chemin_flux(id_camera: int) -> str:
    return f"{PREFIXE}{id_camera}"


class Pont:
    def __init__(self, url_api: str, delai: float) -> None:
        self._url_api = url_api.rstrip("/")
        self._delai = delai

    def reconcilier(self, cameras_actives: Mapping[int, str]) -> None:
        """`cameras_actives` : id → URL RTSP. Lève `OSError` si MediaMTX ne répond pas à la liste."""
        voulus = {chemin_flux(id_camera): url for id_camera, url in cameras_actives.items()}
        presents = self._chemins_camera()
        operations = [("DELETE", f"delete/{nom}", None) for nom in presents.keys() - voulus.keys()]
        for nom, source in voulus.items():
            config = {"source": source, "sourceOnDemand": True}
            if nom not in presents:
                operations.append(("POST", f"add/{nom}", config))
            elif presents[nom] != config:
                operations.append(("PATCH", f"patch/{nom}", config))
        for methode, route, corps in operations:
            try:
                self._appeler(methode, route, corps)
            except OSError as erreur:
                # Sans l'URL : elle peut porter le mot de passe RTSP de la Caméra.
                journal.warning("Pont MediaMTX : %s %s refusé (%s)", methode, route, _raison(erreur))

    def _chemins_camera(self) -> dict[str, dict]:
        chemins: dict[str, dict] = {}
        page, pages = 0, 1
        while page < pages:
            liste = self._appeler("GET", f"list?itemsPerPage={CHEMINS_PAR_PAGE}&page={page}")
            for chemin in liste["items"]:
                if chemin["name"].startswith(PREFIXE):
                    chemins[chemin["name"]] = {
                        "source": chemin["source"],
                        "sourceOnDemand": chemin["sourceOnDemand"],
                    }
            page, pages = page + 1, liste["pageCount"]
        return chemins

    def _appeler(self, methode: str, route: str, corps: dict | None = None) -> dict:
        requete = urllib.request.Request(
            f"{self._url_api}/v3/config/paths/{route}",
            method=methode,
            data=None if corps is None else json.dumps(corps).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(requete, timeout=self._delai) as reponse:
            return json.loads(reponse.read() or b"{}")


def _raison(erreur: OSError) -> str:
    if isinstance(erreur, urllib.error.HTTPError):
        return f"HTTP {erreur.code}"
    return type(erreur).__name__
