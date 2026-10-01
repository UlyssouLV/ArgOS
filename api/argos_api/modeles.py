"""Tables de la base du Site."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
