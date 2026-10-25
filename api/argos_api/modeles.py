"""Tables de la base du Site."""

from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# `raison_etat` d'une Caméra dont l'adresse répond avec une autre MAC que celle de son Appareil : pas relayée.
AUTRE_APPAREIL = "autre_appareil"
# Seules raisons qu'ArgOS écrit dans `raison_etat`.
RaisonEtat = Literal["autre_appareil"]


class Base(DeclarativeBase):
    pass


class SessionAdministrateur(Base):
    """Session ouverte par l'Administrateur. Seule l'empreinte du jeton est stockée."""

    __tablename__ = "sessions"

    empreinte_jeton: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Empreinte du mot de passe en vigueur à l'ouverture : s'il change, la session est refusée.
    empreinte_mot_de_passe: Mapped[str] = mapped_column(String(64))
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Camera(Base):
    """Caméra connue du Site. L'URL RTSP est stockée telle quelle, identifiants en clair (docs/securite.md)."""

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String, unique=True)
    url_rtsp: Mapped[str] = mapped_column(String, unique=True)
    emplacement: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    etat: Mapped[str] = mapped_column(String(16), default="unknown")
    etat_verifie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # MAC de l'Appareil (`aa:bb:cc:dd:ee:ff`), lue sur le réseau, jamais saisie ; non unique.
    mac: Mapped[str | None] = mapped_column(String(17))
    # Pourquoi l'état est ce qu'il est, quand ArgOS le sait (ex. `autre_appareil`).
    raison_etat: Mapped[str | None] = mapped_column(String(32))
    # Nom d'encodage lu dans le SDP (`H264`, `H265`, `MJPEG`…), relevé à l'ajout puis par la sonde ; jamais saisi.
    codec: Mapped[str | None] = mapped_column(String)
    # Port ONVIF qui a répondu à la dernière lecture des Réglages, cherché par ArgOS ; jamais saisi.
    port_onvif: Mapped[int | None] = mapped_column(Integer)
    # Schéma de ce port (`https`, `http`), cherché avec lui (docs/adr/0007-onvif-en-https-par-cle-memorisee.md).
    schema_onvif: Mapped[str | None] = mapped_column(String(5))
    # Empreinte SHA-256 (hexadécimal) de la clé publique du Certificat de l'Appareil, mémorisée au premier contact
    # HTTPS, et sa date : toute autre clé est ensuite refusée.
    empreinte_onvif: Mapped[str | None] = mapped_column(String(64))
    empreinte_onvif_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # L'Administrateur accepte de régler en ONVIF en clair cette caméra sans HTTPS ; révocable.
    onvif_en_clair_accepte: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Enregistrement continu du Flux (docs/adr/0011-enregistrement-continu-par-mediamtx.md) ; OFF à l'ajout.
    enregistrement: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Dernier débit max d'Encodage connu (kbit/s, ONVIF) : repli du Débit d'écriture sans segments récents.
    debit_encodage_kbit_s: Mapped[int | None] = mapped_column(Integer)
    # Dernière vérification de son Horloge (docs/adr/0014-serveur-de-temps-du-site.md,
    # docs/adr/0015-mise-a-l-heure-a-chaque-verification.md) : état (`a_l_heure`, `ecart`, `sans_onvif`, `echec`),
    # dérive avant la Mise à l'heure et écart après, en secondes (positif : la caméra avance), et date ; `None` : jamais.
    horloge_etat: Mapped[str | None] = mapped_column(String(16))
    horloge_derive_s: Mapped[float | None] = mapped_column(Float)
    horloge_ecart_s: Mapped[float | None] = mapped_column(Float)
    horloge_verifiee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReglagesSite(Base):
    """Réglages globaux du Site (une seule ligne, id = 1). Conservation / seuil : ADR 0012 ; Heure du Site : ADR 0014."""

    __tablename__ = "reglages_site"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Durée de Conservation des Segments, en heures (1–24) ; poussée au pont en recordDeleteAfter.
    conservation_h: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Seuil de place disque : octets libres en dessous desquels le Site signale (sans couper).
    seuil_octets_libres: Mapped[int] = mapped_column(
        BigInteger, default=1_073_741_824, server_default="1073741824"
    )
    # Heure du Site : source de l'heure que suit temps (`ntp` : `heure_serveur_ntp`, ou `horloge_serveur`).
    heure_source: Mapped[str] = mapped_column(String(16), default="ntp", server_default="ntp")
    # Gardé quand la source est l'horloge du serveur : il revient si l'Administrateur repasse en NTP.
    heure_serveur_ntp: Mapped[str] = mapped_column(String, default="pool.ntp.org", server_default="pool.ntp.org")
    # Fuseau IANA du Site ; `None` : celui de l'hôte.
    fuseau: Mapped[str | None] = mapped_column(String)
