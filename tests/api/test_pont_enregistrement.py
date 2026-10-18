"""Réconciliation MediaMTX : Enregistrement ON force le tirage continu et `record`."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from argos_api.pont import Pont, Relais


class _Mtx(BaseHTTPRequestHandler):
    chemins: dict[str, dict] = {}

    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/v3/config/paths/list":
            items = [{"name": nom, **config} for nom, config in type(self).chemins.items()]
            self._envoyer(200, {"items": items, "pageCount": 1})
            return
        self._envoyer(404, {})

    def do_POST(self) -> None:
        type(self).chemins[self.path.rsplit("/", 1)[-1]] = json.loads(self._corps())
        self._envoyer(200, {})

    def do_PATCH(self) -> None:
        type(self).chemins[self.path.rsplit("/", 1)[-1]].update(json.loads(self._corps()))
        self._envoyer(200, {})

    def do_DELETE(self) -> None:
        type(self).chemins.pop(self.path.rsplit("/", 1)[-1], None)
        self._envoyer(200, {})

    def _corps(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def _envoyer(self, code: int, corps: dict) -> None:
        brut = json.dumps(corps).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(brut)))
        self.end_headers()
        self.wfile.write(brut)


@pytest.fixture
def pont():
    _Mtx.chemins = {}
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Mtx)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield Pont(f"http://127.0.0.1:{serveur.server_address[1]}", 2)
    serveur.shutdown()


def test_enregistrement_on_ajoute_un_chemin_avec_record_sans_source_a_la_demande(pont):
    pont.reconcilier({3: Relais("rtsp://cam.invalid/flux", True)})

    assert _Mtx.chemins["camera-3"] == {
        "source": "rtsp://cam.invalid/flux",
        "sourceOnDemand": False,
        "record": True,
    }


def test_enregistrement_off_ajoute_un_chemin_a_la_demande_sans_record(pont):
    pont.reconcilier({3: Relais("rtsp://cam.invalid/flux", False)})

    assert _Mtx.chemins["camera-3"] == {
        "source": "rtsp://cam.invalid/flux",
        "sourceOnDemand": True,
        "record": False,
    }


def test_passage_on_vers_off_met_a_jour_le_chemin(pont):
    pont.reconcilier({3: Relais("rtsp://cam.invalid/flux", True)})

    pont.reconcilier({3: Relais("rtsp://cam.invalid/flux", False)})

    assert _Mtx.chemins["camera-3"]["sourceOnDemand"] is True
    assert _Mtx.chemins["camera-3"]["record"] is False
