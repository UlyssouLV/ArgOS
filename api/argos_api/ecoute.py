"""Écoute de l'API : le réseau des caméras est une sortie, jamais une entrée (ADR 0003, docs/securite.md).

Une requête arrivée sur une adresse d'ArgOS du réseau des caméras (macvlan) est refusée avant tout
traitement : ni routage, ni session. Le healthcheck (`localhost`) et le bridge restent servis.
"""

import json
from collections.abc import Collection
from ipaddress import IPv4Address

from starlette.types import ASGIApp, Receive, Scope, Send

REFUSEE = "Requête refusée : arrivée par le réseau des caméras, qui n'est qu'une sortie d'ArgOS."


class SortieSeulement:
    """Middleware ASGI, le plus extérieur : refuse les connexions arrivées sur une des `adresses` locales."""

    def __init__(self, app: ASGIApp, adresses: Collection[IPv4Address]) -> None:
        self.app = app
        self.adresses = {str(adresse) for adresse in adresses}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        serveur = scope.get("server")
        if scope["type"] == "lifespan" or not serveur or serveur[0] not in self.adresses:
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            corps = json.dumps({"detail": REFUSEE}, ensure_ascii=False).encode()
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(corps)).encode())],
            })
            await send({"type": "http.response.body", "body": corps})
