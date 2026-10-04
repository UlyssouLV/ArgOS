"""Sonde RTSP : une Caméra livre-t-elle au moins un paquet RTP vidéo dans le délai ?

Session `DESCRIBE` / `SETUP` / `PLAY` en RTP entrelacé sur la connexion TCP (aucun port UDP à
ouvrir), identifiants de l'URL pris en charge (Basic ou Digest), puis `TEARDOWN`. Sans ffmpeg.
"""

import base64
import hashlib
import re
import secrets
import socket
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

PORT_RTSP = 554
CANAL_VIDEO = 0
TAILLE_ENTETE_RTP = 12


class _Echec(Exception):
    """La Caméra a répondu autre chose qu'attendu : pas de vidéo."""


def sonder(url: str, delai: float) -> bool:
    """Vrai si au moins un paquet RTP vidéo arrive dans `delai` secondes ; faux sinon, sans lever."""
    try:
        with _SessionRtsp(url, time.monotonic() + delai) as session:
            return session.recoit_de_la_video()
    except (OSError, ValueError, _Echec):
        return False


@dataclass(frozen=True)
class Description:
    """Réponse à `DESCRIBE` : son statut et, si `200`, le codec de la première piste vidéo du SDP."""

    statut: int
    codec: str | None


def decrire(url: str, delai: float) -> Description | None:
    """`DESCRIBE` sur `url` dans `delai` secondes ; `None` sans réponse RTSP, sans lever."""
    try:
        with _SessionRtsp(url, time.monotonic() + delai) as session:
            reponse = session.decrire()
    except (OSError, ValueError, _Echec):
        return None
    codec = _codec_video(reponse.corps.decode(errors="replace")) if reponse.statut == 200 else None
    return Description(reponse.statut, codec)


class _SessionRtsp:
    def __init__(self, url: str, echeance: float) -> None:
        morceaux = urlsplit(url)
        if morceaux.scheme != "rtsp" or not morceaux.hostname:
            raise ValueError(url)
        self._echeance = echeance
        self._utilisateur = unquote(morceaux.username or "")
        self._mot_de_passe = unquote(morceaux.password or "")
        # Les identifiants ne voyagent que dans l'en-tête Authorization, jamais dans l'URL.
        hote = morceaux.hostname if ":" not in morceaux.hostname else f"[{morceaux.hostname}]"
        netloc = hote if morceaux.port is None else f"{hote}:{morceaux.port}"
        self._url = morceaux._replace(netloc=netloc).geturl()
        self._defi: dict[str, str] | None = None
        self._cseq = 0
        self._session: str | None = None
        self._tampon = b""
        self._socket = socket.create_connection(
            (morceaux.hostname, morceaux.port or PORT_RTSP), timeout=self._restant()
        )

    def __enter__(self) -> "_SessionRtsp":
        return self

    def __exit__(self, *_: object) -> None:
        try:
            if self._session is not None:
                self._envoyer("TEARDOWN", self._url)
        except OSError:
            pass
        finally:
            self._socket.close()

    def decrire(self) -> "_Reponse":
        return self._echanger("DESCRIBE", self._url, {"Accept": "application/sdp"})

    def recoit_de_la_video(self) -> bool:
        description = self.decrire()
        if description.statut != 200:
            raise _Echec(f"DESCRIBE : {description.statut}")
        base = description.entetes.get("content-base") or description.entetes.get("content-location") or self._url
        piste = _piste_video(description.corps.decode(errors="replace"), base)
        configuration = self._requete(
            "SETUP", piste, {"Transport": f"RTP/AVP/TCP;unicast;interleaved={CANAL_VIDEO}-{CANAL_VIDEO + 1}"}
        )
        session = configuration.entetes.get("session")
        if not session:
            raise _Echec("SETUP sans Session")
        self._session = session.split(";")[0].strip()
        self._requete("PLAY", self._url, {"Range": "npt=0.000-"})
        while True:
            canal, paquet = self._lire_trame()
            if canal == CANAL_VIDEO and len(paquet) >= TAILLE_ENTETE_RTP and paquet[0] >> 6 == 2:
                return True

    # Requêtes et réponses

    def _requete(self, methode: str, url: str, entetes: dict[str, str]) -> "_Reponse":
        reponse = self._echanger(methode, url, entetes)
        if reponse.statut != 200:
            raise _Echec(f"{methode} : {reponse.statut}")
        return reponse

    def _echanger(self, methode: str, url: str, entetes: dict[str, str]) -> "_Reponse":
        """Requête et réponse, quel qu'en soit le statut ; identifiants présentés une fois si la Caméra les demande."""
        self._envoyer(methode, url, entetes)
        reponse = self._lire_reponse()
        if reponse.statut == 401 and self._defi is None and self._utilisateur:
            self._defi = _lire_defi(reponse.entetes.get("www-authenticate", ""))
            self._envoyer(methode, url, entetes)
            reponse = self._lire_reponse()
        return reponse

    def _envoyer(self, methode: str, url: str, entetes: dict[str, str] | None = None) -> None:
        self._cseq += 1
        lignes = [f"{methode} {url} RTSP/1.0", f"CSeq: {self._cseq}", "User-Agent: ArgOS"]
        lignes += [f"{nom}: {valeur}" for nom, valeur in (entetes or {}).items()]
        if self._session is not None:
            lignes.append(f"Session: {self._session}")
        if self._defi is not None:
            lignes.append(f"Authorization: {self._autorisation(methode, url)}")
        self._socket.settimeout(self._restant())
        self._socket.sendall(("\r\n".join(lignes) + "\r\n\r\n").encode())

    def _autorisation(self, methode: str, url: str) -> str:
        defi = self._defi
        if defi["schema"] == "basic":
            jeton = base64.b64encode(f"{self._utilisateur}:{self._mot_de_passe}".encode()).decode()
            return f"Basic {jeton}"
        ha1 = _md5(f"{self._utilisateur}:{defi.get('realm', '')}:{self._mot_de_passe}")
        ha2 = _md5(f"{methode}:{url}")
        champs = {"username": self._utilisateur, "realm": defi.get("realm", ""), "nonce": defi.get("nonce", ""), "uri": url}
        if "auth" in defi.get("qop", "").split(","):
            cnonce, nc = secrets.token_hex(8), f"{self._cseq:08x}"
            champs |= {"qop": "auth", "nc": nc, "cnonce": cnonce}
            champs["response"] = _md5(f"{ha1}:{champs['nonce']}:{nc}:{cnonce}:auth:{ha2}")
        else:
            champs["response"] = _md5(f"{ha1}:{champs['nonce']}:{ha2}")
        if "opaque" in defi:
            champs["opaque"] = defi["opaque"]
        # qop et nc ne sont pas entre guillemets (RFC 7616).
        return "Digest " + ", ".join(
            f"{nom}={valeur}" if nom in ("qop", "nc") else f'{nom}="{valeur}"' for nom, valeur in champs.items()
        )

    def _lire_reponse(self) -> "_Reponse":
        while True:
            if self._regarder(1) == b"$":
                self._lire_trame()  # Paquet en avance sur la réponse : ignoré.
                continue
            statut = self._lire_ligne().split(" ", 2)
            if len(statut) < 2 or not statut[0].startswith("RTSP/"):
                raise _Echec("réponse RTSP attendue")
            entetes: dict[str, str] = {}
            while ligne := self._lire_ligne():
                nom, _, valeur = ligne.partition(":")
                entetes[nom.strip().lower()] = valeur.strip()
            corps = self._lire(int(entetes.get("content-length", "0")))
            return _Reponse(int(statut[1]), entetes, corps)

    def _lire_trame(self) -> tuple[int, bytes]:
        """Trame entrelacée : `$`, canal (1 octet), longueur (2 octets), paquet. Ignore le texte RTSP entre deux."""
        while self._regarder(1) != b"$":
            self._lire_reponse()
        entete = self._lire(4)
        return entete[1], self._lire(int.from_bytes(entete[2:4], "big"))

    # Lecture bornée par l'échéance

    def _restant(self) -> float:
        restant = self._echeance - time.monotonic()
        if restant <= 0:
            raise TimeoutError
        return restant

    def _remplir(self, taille: int) -> None:
        while len(self._tampon) < taille:
            self._socket.settimeout(self._restant())
            donnees = self._socket.recv(65536)
            if not donnees:
                raise ConnectionError("connexion fermée")
            self._tampon += donnees

    def _regarder(self, taille: int) -> bytes:
        self._remplir(taille)
        return self._tampon[:taille]

    def _lire(self, taille: int) -> bytes:
        self._remplir(taille)
        donnees, self._tampon = self._tampon[:taille], self._tampon[taille:]
        return donnees

    def _lire_ligne(self) -> str:
        while b"\r\n" not in self._tampon:
            self._remplir(len(self._tampon) + 1)
        ligne, _, self._tampon = self._tampon.partition(b"\r\n")
        return ligne.decode(errors="replace")


class _Reponse:
    def __init__(self, statut: int, entetes: dict[str, str], corps: bytes) -> None:
        self.statut = statut
        self.entetes = entetes
        self.corps = corps


def _piste_video(sdp: str, base: str) -> str:
    """URL de contrôle de la première piste vidéo du SDP, résolue contre `base`."""
    medias = re.split(r"^m=", sdp, flags=re.MULTILINE)
    for media in medias[1:]:
        if not media.startswith("video"):
            continue
        controle = re.search(r"^a=control:\s*(\S+)", media, flags=re.MULTILINE)
        if controle is None or controle.group(1) == "*":
            return base
        if controle.group(1).startswith("rtsp://"):
            return controle.group(1)
        # Concaténée, comme ffmpeg : la base peut porter une requête (`?…`) qu'urljoin perdrait.
        return (base if base.endswith("/") else base + "/") + controle.group(1)
    raise _Echec("aucune piste vidéo")


def _codec_video(sdp: str) -> str | None:
    """Nom d'encodage (`H264`, `H265`…) du premier format de la première piste vidéo, d'après son `a=rtpmap`."""
    for media in re.split(r"^m=", sdp, flags=re.MULTILINE)[1:]:
        if not media.startswith("video"):
            continue
        formats = media.partition("\n")[0].split()[3:]
        if not formats:
            return None
        carte = re.search(rf"^a=rtpmap:{re.escape(formats[0])}\s+([^/\s]+)", media, flags=re.MULTILINE)
        return carte.group(1).upper() if carte else None
    return None


def _lire_defi(entete: str) -> dict[str, str]:
    schema, _, reste = entete.partition(" ")
    defi = {cle.lower(): valeur for cle, valeur in re.findall(r'(\w+)="?([^",]*)"?', reste)}
    return defi | {"schema": schema.lower()}


def _md5(texte: str) -> str:
    return hashlib.md5(texte.encode()).hexdigest()
