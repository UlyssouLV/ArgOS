"""Relecture vidéo seule (docs/adr/0013-relecture-des-enregistrements.md, bug #141).

Le serveur playback du pont sert un MP4 progressif (`ftyp`, `moov`, `mdat`) avec toutes les pistes du Flux. Une
piste audio PCM (`ipcm`) fait refuser le fichier par Safari : seules les pistes vidéo restent dans `moov`, sans
réencodage. Les octets audio restent dans `mdat`, plus désignés par aucune piste ; les tables de morceaux (`stco`,
`co64`) des pistes vidéo suivent le `moov` raccourci. Aucun autre octet n'est touché, et un MP4 sans piste à
retirer (ou sans piste vidéo) passe tel quel. Sans dépendance hors stdlib.

Safari ouvre une `<video>` par `Range: bytes=0-1` et refuse tout sauf un `206` (#143) : `servir_par_plages` répond
à cet en-tête.

Une caméra qui horodate son audio en avance sur sa vidéo (Cam 01, #172) fait ouvrir au pont chaque Segment à l'heure
de l'audio : la vidéo arrivée « trop tard » est jetée, et la vidéo du Segment, qui finit à sa fin réelle, commence
plus tard que son nom. `recaler` décale d'autant la fenêtre demandée, pour lire l'image de l'instant visé.
"""

import re
import struct
import urllib.parse
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

# Boîtes qui ne contiennent que des boîtes, de `trak` jusqu'aux tables de morceaux.
CONTENEURS = {b"trak", b"mdia", b"minf", b"stbl"}
GESTIONNAIRE_VIDEO = b"vide"
# recordPath du pont (media/mediamtx.yml) : `%Y-%m-%d_%H-%M-%S-%f`, heure UTC du conteneur, suffixe `.mp4`.
FORMAT_NOM_SEGMENT = "%Y-%m-%d_%H-%M-%S-%f"
SUFFIXE_SEGMENT = ".mp4"
# Chemin du pont d'une Caméra (`camera-<id>`, ADR 0011) : seul nom de dossier lu sous la racine des enregistrements.
CHEMIN_CAMERA = re.compile(r"camera-\d+")
# Écart (s) entre heure réelle et vidéo d'un Segment en deçà duquel la fenêtre ne bouge pas : la dernière image et la
# dernière écriture du fichier ne tombent jamais pile ensemble. Même tolérance que la contiguïté des Segments.
ECART_MIN_S = 1.0
# Une seule plage, `a-b`, `a-` ou `-n` (RFC 9110, 14.1.2) ; plusieurs plages font servir le fichier entier.
PLAGE = re.compile(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*")


class PlageInsatisfaisable(ValueError):
    """La plage demandée commence après la fin du fichier : `416`."""


def plage(entete: str | None, taille: int) -> tuple[int, int] | None:
    """Bornes [début, fin[ de l'en-tête `Range` sur `taille` octets ; None s'il est absent ou illisible (`200`)."""
    correspondance = PLAGE.fullmatch(entete or "")
    if correspondance is None:
        return None
    premier, dernier = correspondance.groups()
    if not premier:
        if not dernier:
            return None
        suffixe = int(dernier)
        if suffixe == 0 or taille == 0:
            raise PlageInsatisfaisable
        return max(taille - suffixe, 0), taille
    debut = int(premier)
    if dernier and int(dernier) < debut:
        return None
    if debut >= taille:
        raise PlageInsatisfaisable
    return debut, min(int(dernier) + 1, taille) if dernier else taille


def servir_par_plages(mp4: bytes, entete: str | None) -> tuple[int, dict[str, str], bytes]:
    """Statut, en-têtes et corps de la réponse à l'en-tête `Range` : `200` le fichier entier, `206` une plage, `416`
    une plage hors du fichier."""
    try:
        bornes = plage(entete, len(mp4))
    except PlageInsatisfaisable:
        return 416, {"Content-Range": f"bytes */{len(mp4)}"}, b""
    if bornes is None:
        return 200, {"Accept-Ranges": "bytes"}, mp4
    debut, fin = bornes
    return 206, {"Accept-Ranges": "bytes", "Content-Range": f"bytes {debut}-{fin - 1}/{len(mp4)}"}, mp4[debut:fin]


def recaler_la_requete(racine: Path, requete: str) -> str:
    """Requête `/get` (`path`, `start` RFC 3339, `duration` en secondes…) avec sa fenêtre recalée par `recaler` ;
    telle quelle si elle ne se lit pas : le pont répond lui-même à une requête invalide."""
    parametres = urllib.parse.parse_qs(requete, keep_blank_values=True)
    try:
        (chemin,), (start,), (duration,) = parametres["path"], parametres["start"], parametres["duration"]
        debut, duree_s = datetime.fromisoformat(start), float(duration)
    except (KeyError, ValueError):
        return requete
    if debut.tzinfo is None:
        return requete
    recale, duree = recaler(racine, chemin, debut.astimezone(UTC), duree_s)
    if (recale, duree) == (debut, duree_s):
        return requete
    parametres["start"] = [recale.isoformat().replace("+00:00", "Z")]
    parametres["duration"] = [f"{duree:.6f}"]
    return urllib.parse.urlencode(parametres, doseq=True)


def recaler(racine: Path, chemin: str, debut: datetime, duree_s: float) -> tuple[datetime, float]:
    """Fenêtre (`start`, `duration`) à demander au pont pour lire l'image de `debut`. Le Segment qui le couvre a moins
    de vidéo que d'heure réelle : sa vidéo finit à sa fin (début du suivant, sinon dernière écriture), et le pont la
    place depuis son début ; le début de la fenêtre recule de l'écart, sans passer avant le Segment. Sa fin ne bouge
    pas : l'audio, en avance, précède la vidéo dans le fichier, et le pont s'arrête au premier échantillon qui dépasse
    la fenêtre, toutes pistes confondues. Hors d'un Segment connu, ou à vidéo complète, elle passe telle quelle."""
    if not CHEMIN_CAMERA.fullmatch(chemin):
        return debut, duree_s
    segments = sorted(segments_du_dossier(racine / chemin))
    for (debut_segment, fichier), suivant in zip(segments, [*segments[1:], None]):
        try:
            fin = datetime.fromtimestamp(fichier.stat().st_mtime, UTC)
        except OSError:
            return debut, duree_s
        if suivant is not None:
            fin = min(fin, suivant[0])
        if not debut_segment <= debut < fin:
            continue
        video = fin_de_la_video(fichier)
        ecart = (fin - debut_segment).total_seconds() - (video or 0)
        if video is None or ecart < ECART_MIN_S:
            return debut, duree_s
        recale = max(debut_segment, debut - timedelta(seconds=ecart))
        return recale, (debut + timedelta(seconds=duree_s) - recale).total_seconds()
    return debut, duree_s


def fin_de_la_video(fichier: Path) -> float | None:
    """Fin (s) de la piste vidéo d'un Segment fMP4 du pont, depuis son début ; None sans vidéo ou s'il est illisible."""
    try:
        with fichier.open("rb") as flux:
            piste, fin = None, None
            for type_, contenu in _boites_du_fichier(flux, {b"moov", b"moof"}):
                if type_ == b"moov":
                    piste = _piste_video(contenu)
                elif piste is not None:
                    for fin_traf in _fins_dans_le_fragment(contenu, piste[0]):
                        fin = fin_traf if fin is None else max(fin, fin_traf)
    except (OSError, struct.error, IndexError):
        return None
    return None if piste is None or fin is None else fin / piste[1]


def segments_du_dossier(dossier: Path) -> list[tuple[datetime, Path]]:
    """Segments du dossier repérés par le début lu dans leur nom, sans toucher aux fichiers ; aucun s'il est illisible."""
    try:
        chemins = list(dossier.iterdir())
    except OSError:
        return []
    lus = []
    for chemin in chemins:
        if chemin.suffix != SUFFIXE_SEGMENT:
            continue
        try:
            lus.append((datetime.strptime(chemin.stem, FORMAT_NOM_SEGMENT).replace(tzinfo=UTC), chemin))
        except ValueError:
            continue
    return lus


def _boites_du_fichier(flux: BinaryIO, voulues: set[bytes]) -> Iterator[tuple[bytes, bytes]]:
    """(type, boîte entière) des boîtes de premier niveau de type `voulues` ; les autres sont sautées sans être lues.
    S'arrête à la première boîte tronquée ou mal formée."""
    while len(entete := flux.read(8)) == 8:
        taille, type_ = struct.unpack(">I4s", entete)
        if taille == 1:
            suite = flux.read(8)
            if len(suite) < 8:
                return
            entete += suite
            (taille,) = struct.unpack(">Q", suite)
        if taille < len(entete):
            return
        if type_ not in voulues:
            flux.seek(taille - len(entete), 1)
            continue
        contenu = flux.read(taille - len(entete))
        if len(contenu) < taille - len(entete):
            return
        yield type_, entete + contenu


def _piste_video(moov: bytes) -> tuple[int, int] | None:
    """(identifiant, échelle de temps) de la première piste vidéo de `moov`."""
    for type_, debut, fin in _boites(moov, 8, len(moov)):
        if type_ != b"trak" or _gestionnaire(moov, debut, fin) != GESTIONNAIRE_VIDEO:
            continue
        identifiant = echelle = None
        for type_enfant, debut_enfant, _ in _boites(moov, debut + 8, fin):
            if type_enfant == b"tkhd":
                identifiant = _champ_versionne(moov, debut_enfant, 12)
            elif type_enfant == b"mdia":
                for type_mdhd, debut_mdhd, _ in _boites(moov, debut_enfant + 8, fin):
                    if type_mdhd == b"mdhd":
                        echelle = _champ_versionne(moov, debut_mdhd, 12)
        if identifiant is not None and echelle:
            return identifiant, echelle
    return None


def _champ_versionne(octets: bytes, debut: int, decalage_v0: int) -> int:
    """Champ 32 bits après les dates de création et de modification d'une boîte complète (`tkhd`, `mdhd`) : 32 bits
    chacune en version 0, 64 en version 1."""
    position = debut + 8 + decalage_v0 + (8 if octets[debut + 8] == 1 else 0)
    return struct.unpack(">I", octets[position : position + 4])[0]


def _fins_dans_le_fragment(moof: bytes, piste: int) -> Iterator[int]:
    """Fin (`tfdt` + durées des échantillons, dans l'échelle de la piste) de chaque `traf` de `piste` dans `moof`."""
    for type_, debut, fin in _boites(moof, 8, len(moof)):
        if type_ != b"traf":
            continue
        enfants = {t: (d, f) for t, d, f in _boites(moof, debut + 8, fin)}
        if b"tfhd" not in enfants or b"tfdt" not in enfants or b"trun" not in enfants:
            continue
        debut_tfhd = enfants[b"tfhd"][0]
        drapeaux_tfhd = int.from_bytes(moof[debut_tfhd + 9 : debut_tfhd + 12])
        if struct.unpack(">I", moof[debut_tfhd + 12 : debut_tfhd + 16])[0] != piste:
            continue
        # Durée par défaut : après l'identifiant, le décalage de base (8 octets) et l'index de description (4).
        position = debut_tfhd + 16 + (8 if drapeaux_tfhd & 0x01 else 0) + (4 if drapeaux_tfhd & 0x02 else 0)
        defaut = struct.unpack(">I", moof[position : position + 4])[0] if drapeaux_tfhd & 0x08 else 0
        debut_tfdt = enfants[b"tfdt"][0]
        if moof[debut_tfdt + 8] == 1:
            (base,) = struct.unpack(">Q", moof[debut_tfdt + 12 : debut_tfdt + 20])
        else:
            (base,) = struct.unpack(">I", moof[debut_tfdt + 12 : debut_tfdt + 16])
        yield base + sum(_durees(moof, enfants[b"trun"][0], defaut))


def _durees(moof: bytes, debut: int, defaut: int) -> Iterator[int]:
    """Durée de chaque échantillon d'un `trun` ; `defaut` (celle du `tfhd`) s'il n'en porte pas."""
    drapeaux = int.from_bytes(moof[debut + 9 : debut + 12])
    (nombre,) = struct.unpack(">I", moof[debut + 12 : debut + 16])
    position = debut + 16 + (4 if drapeaux & 0x01 else 0) + (4 if drapeaux & 0x04 else 0)
    # Champs par échantillon : durée, taille, drapeaux, décalage de composition, 4 octets chacun s'il est présent.
    pas = 4 * sum(1 for bit in (0x100, 0x200, 0x400, 0x800) if drapeaux & bit)
    for _ in range(nombre):
        if drapeaux & 0x100:
            yield struct.unpack(">I", moof[position : position + 4])[0]
        else:
            yield defaut
        position += pas


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
