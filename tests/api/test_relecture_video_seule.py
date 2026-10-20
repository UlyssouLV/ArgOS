"""Relecture vidéo seule (bug #141) : pistes non vidéo retirées du MP4 du serveur playback (tests unitaires).

Le test de bout en bout (Caméra simulée 4, qui annonce une piste audio `ipcm`) est dans test_relecture.py.
"""

import struct

import pytest

from argos_api import relecture

VIDEO = b"V" * 40
AUDIO = b"A" * 24


def boite(type_: bytes, *contenus: bytes) -> bytes:
    contenu = b"".join(contenus)
    return struct.pack(">I4s", 8 + len(contenu), type_) + contenu


def boite_complete(type_: bytes, contenu: bytes) -> bytes:
    return boite(type_, b"\0\0\0\0" + contenu)


def table_des_morceaux(decalages: list[int], co64: bool) -> bytes:
    format_ = ">Q" if co64 else ">I"
    entrees = b"".join(struct.pack(format_, d) for d in decalages)
    return boite_complete(b"co64" if co64 else b"stco", struct.pack(">I", len(decalages)) + entrees)


def piste(gestionnaire: bytes, decalages: list[int], co64: bool = False) -> bytes:
    hdlr = boite_complete(b"hdlr", b"\0\0\0\0" + gestionnaire + b"\0" * 13)
    stbl = boite(b"stbl", boite_complete(b"stsd", b"\0\0\0\0"), table_des_morceaux(decalages, co64))
    return boite(b"trak", boite_complete(b"tkhd", b"\0" * 80), boite(b"mdia", hdlr, boite(b"minf", stbl)))


FTYP = boite(b"ftyp", b"isom\0\0\x02\0isomiso2")
MVHD = boite_complete(b"mvhd", b"\0" * 96)


def mp4(pistes: list[tuple[bytes, bytes]], co64: bool = False, moov_a_la_fin: bool = False) -> bytes:
    """MP4 progressif, un morceau par piste dans `mdat` ; les tables de morceaux pointent sur leurs octets."""

    def moov(debut_mdat: int) -> bytes:
        decalages, position = [], debut_mdat + 8
        for _, donnees in pistes:
            decalages.append(position)
            position += len(donnees)
        return boite(b"moov", MVHD, *(piste(g, [d], co64) for (g, _), d in zip(pistes, decalages)))

    mdat = boite(b"mdat", *(donnees for _, donnees in pistes))
    if moov_a_la_fin:
        return FTYP + mdat + moov(len(FTYP))
    return FTYP + moov(len(FTYP) + len(moov(0))) + mdat


def boites(octets: bytes, debut: int = 0, fin: int | None = None) -> list[tuple[bytes, int, int]]:
    """(type, début, taille) des boîtes de `octets[debut:fin]`."""
    fin = len(octets) if fin is None else fin
    trouvees = []
    while debut < fin:
        taille, type_ = struct.unpack(">I4s", octets[debut : debut + 8])
        trouvees.append((type_, debut, taille))
        debut += taille
    return trouvees


def enfant(octets: bytes, chemin: list[bytes], debut: int = 0, fin: int | None = None) -> list[tuple[int, int]]:
    """(début, taille) des boîtes au bout de `chemin`, en descendant dans les conteneurs."""
    type_, *reste = chemin
    resultats = []
    for t, d, taille in boites(octets, debut, fin):
        if t != type_:
            continue
        if not reste:
            resultats.append((d, taille))
        else:
            resultats += enfant(octets, reste, d + 8, d + taille)
    return resultats


def gestionnaires(octets: bytes) -> list[bytes]:
    return [octets[d + 16 : d + 20] for d, _ in enfant(octets, [b"moov", b"trak", b"mdia", b"hdlr"])]


def octets_pointes(octets: bytes, longueur: int) -> list[bytes]:
    """Octets désignés par chaque table de morceaux (`stco` ou `co64`) des pistes restantes."""
    pointes = []
    for nom, format_ in ((b"stco", ">I"), (b"co64", ">Q")):
        for d, _ in enfant(octets, [b"moov", b"trak", b"mdia", b"minf", b"stbl", nom]):
            (nombre,) = struct.unpack(">I", octets[d + 12 : d + 16])
            pas = struct.calcsize(format_)
            for i in range(nombre):
                (decalage,) = struct.unpack(format_, octets[d + 16 + i * pas : d + 16 + (i + 1) * pas])
                pointes.append(octets[decalage : decalage + longueur])
    return pointes


def relu(octets: bytes, taille_morceau: int = 7) -> bytes:
    return b"".join(relecture.video_seule(octets[i : i + taille_morceau] for i in range(0, len(octets), taille_morceau)))


@pytest.mark.parametrize("co64", [False, True])
def test_la_piste_audio_est_retiree_et_la_video_pointe_toujours_sur_ses_octets(co64):
    source = mp4([(b"vide", VIDEO), (b"soun", AUDIO)], co64=co64)
    assert octets_pointes(source, len(VIDEO))[0] == VIDEO

    sortie = relu(source)

    assert gestionnaires(sortie) == [b"vide"]
    assert octets_pointes(sortie, len(VIDEO)) == [VIDEO]
    assert [t for t, _, _ in boites(sortie)] == [b"ftyp", b"moov", b"mdat"]


def test_la_piste_audio_avant_la_video_est_retiree_aussi():
    sortie = relu(mp4([(b"soun", AUDIO), (b"vide", VIDEO)]))

    assert gestionnaires(sortie) == [b"vide"]
    assert octets_pointes(sortie, len(VIDEO)) == [VIDEO]


def test_un_moov_apres_mdat_garde_les_decalages_de_la_video():
    sortie = relu(mp4([(b"vide", VIDEO), (b"soun", AUDIO)], moov_a_la_fin=True))

    assert gestionnaires(sortie) == [b"vide"]
    assert octets_pointes(sortie, len(VIDEO)) == [VIDEO]


def test_un_mp4_video_seule_passe_tel_quel():
    source = mp4([(b"vide", VIDEO)])

    assert relu(source) == source


def test_un_mp4_sans_piste_video_passe_tel_quel():
    source = mp4([(b"soun", AUDIO)])

    assert relu(source) == source


def test_le_decoupage_du_flux_ne_change_pas_le_resultat():
    source = mp4([(b"vide", VIDEO), (b"soun", AUDIO)])

    assert relu(source, 1) == relu(source, len(source))


def test_un_flux_tronque_est_transmis_sans_erreur():
    source = mp4([(b"vide", VIDEO), (b"soun", AUDIO)])

    assert relu(source[:20]) == source[:20]
