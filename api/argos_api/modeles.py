"""Tables de la base du Site."""

from datetime import datetime

from sqlalchemy import DateTime, String
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
