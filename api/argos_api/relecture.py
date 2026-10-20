"""Relecture vidéo seule (docs/adr/0013-relecture-des-enregistrements.md, bug #141).

Le serveur playback du pont sert un MP4 progressif (`ftyp`, `moov`, `mdat`) avec toutes les pistes du Flux. Une
piste audio PCM (`ipcm`) fait refuser le fichier par Safari : seules les pistes vidéo restent dans `moov`, sans
réencodage. Les octets audio restent dans `mdat`, plus désignés par aucune piste ; les tables de morceaux (`stco`,
`co64`) des pistes vidéo suivent le `moov` raccourci. Aucun autre octet n'est touché, et un MP4 sans piste à
retirer (ou sans piste vidéo) passe tel quel. Sans dépendance hors stdlib.
"""

import struct
from collections.abc import Iterable, Iterator

# Boîtes qui ne contiennent que des boîtes, de `trak` jusqu'aux tables de morceaux.
CONTENEURS = {b"trak", b"mdia", b"minf", b"stbl"}
GESTIONNAIRE_VIDEO = b"vide"


def video_seule(morceaux: Iterable[bytes]) -> Iterator[bytes]:
    """Le MP4 de `morceaux` sans ses pistes non vidéo, en flux : seul `moov` est tenu en mémoire."""
    lecteur = _Lecteur(iter(morceaux))
    position = 0
    while True:
        entete = lecteur.lire(8)
        if len(entete) < 8:
            yield entete
            return
        taille, type_ = struct.unpack(">I4s", entete)
        if taille == 1:
            entete += lecteur.lire(8)
            if len(entete) < 16:
                yield entete
                return
            (taille,) = struct.unpack(">Q", entete[8:])
        if taille < len(entete):
            # Taille 0 (jusqu'à la fin) ou invalide : le reste passe tel quel.
            yield entete
            yield from lecteur.reste()
            return
        if type_ == b"moov":
            moov = entete + lecteur.lire(taille - len(entete))
            yield _moov_video_seule(moov, position) if len(moov) == taille else moov
            yield from lecteur.reste()
            return
        yield entete
        yield from lecteur.transmettre(taille - len(entete))
        position += taille


def _moov_video_seule(moov: bytes, debut: int) -> bytes:
    entete = 16 if struct.unpack(">I", moov[:4])[0] == 1 else 8
    enfants = list(_boites(moov, entete, len(moov)))
    gardes = [
        (type_, debut_boite, fin_boite)
        for type_, debut_boite, fin_boite in enfants
        if type_ != b"trak" or _gestionnaire(moov, debut_boite, fin_boite) == GESTIONNAIRE_VIDEO
    ]
    if len(gardes) == len(enfants) or not any(type_ == b"trak" for type_, _, _ in gardes):
        return moov
    contenu = bytearray(b"".join(moov[debut_boite:fin_boite] for _, debut_boite, fin_boite in gardes))
    nouveau = bytearray(struct.pack(">I4s", 8 + len(contenu), b"moov")) + contenu
    # Seules les données placées après `moov` se rapprochent du début du fichier.
    retrait, fin = len(moov) - len(nouveau), debut + len(moov)
    for type_, debut_piste, fin_piste in _boites(nouveau, 8, len(nouveau)):
        if type_ == b"trak":
            _decaler_les_morceaux(nouveau, debut_piste, fin_piste, fin, retrait)
    return bytes(nouveau)


def _gestionnaire(octets: bytes, debut: int, fin: int) -> bytes | None:
    """Type de gestionnaire (`vide`, `soun`…) du `hdlr` de la piste `octets[debut:fin]`."""
    for type_, debut_mdia, fin_mdia in _boites(octets, debut + 8, fin):
        if type_ == b"mdia":
            for type_enfant, debut_hdlr, fin_hdlr in _boites(octets, debut_mdia + 8, fin_mdia):
                if type_enfant == b"hdlr" and fin_hdlr - debut_hdlr >= 20:
                    return octets[debut_hdlr + 16 : debut_hdlr + 20]
    return None


def _decaler_les_morceaux(octets: bytearray, debut: int, fin: int, seuil: int, retrait: int) -> None:
    """Retire `retrait` aux décalages ≥ `seuil` des tables de morceaux de la boîte `octets[debut:fin]`."""
    for type_, debut_boite, fin_boite in _boites(octets, debut + 8, fin):
        if type_ in CONTENEURS:
            _decaler_les_morceaux(octets, debut_boite, fin_boite, seuil, retrait)
        elif type_ in (b"stco", b"co64"):
            format_ = ">I" if type_ == b"stco" else ">Q"
            pas = struct.calcsize(format_)
            # Boîte complète : version et drapeaux (4 octets), nombre d'entrées (4), puis les entrées.
            (nombre,) = struct.unpack(">I", octets[debut_boite + 12 : debut_boite + 16])
            premiere = debut_boite + 16
            for position in range(premiere, min(premiere + nombre * pas, fin_boite), pas):
                (decalage,) = struct.unpack(format_, octets[position : position + pas])
                if decalage >= seuil:
                    struct.pack_into(format_, octets, position, decalage - retrait)


def _boites(octets: bytes | bytearray, debut: int, fin: int) -> Iterator[tuple[bytes, int, int]]:
    """(type, début, fin) des boîtes de `octets[debut:fin]` ; s'arrête à la première boîte mal formée."""
    while debut + 8 <= fin:
        taille, type_ = struct.unpack(">I4s", octets[debut : debut + 8])
        if taille < 8 or debut + taille > fin:
            return
        yield bytes(type_), debut, debut + taille
        debut += taille


class _Lecteur:
    """Octets d'un flux découpé en morceaux quelconques, lus à la demande."""

    def __init__(self, morceaux: Iterator[bytes]) -> None:
        self._morceaux = morceaux
        self._tampon = b""

    def lire(self, nombre: int) -> bytes:
        """Jusqu'à `nombre` octets ; moins seulement à la fin du flux."""
        parties, manque = [], nombre
        while manque > 0:
            partie = self._prendre(manque)
            if not partie:
                break
            parties.append(partie)
            manque -= len(partie)
        return b"".join(parties)

    def transmettre(self, nombre: int) -> Iterator[bytes]:
        while nombre > 0:
            partie = self._prendre(nombre)
            if not partie:
                return
            nombre -= len(partie)
            yield partie

    def reste(self) -> Iterator[bytes]:
        if self._tampon:
            yield self._tampon
            self._tampon = b""
        yield from self._morceaux

    def _prendre(self, nombre: int) -> bytes:
        while not self._tampon:
            morceau = next(self._morceaux, None)
            if morceau is None:
                return b""
            self._tampon = morceau
        partie, self._tampon = self._tampon[:nombre], self._tampon[nombre:]
        return partie
