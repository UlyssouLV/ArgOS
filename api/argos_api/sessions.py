"""Connexion de l'Administrateur : vérification des identifiants et sessions en base."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from argos_api.configuration import Configuration
from argos_api.modeles import SessionAdministrateur

DUREE = timedelta(hours=24)


def identifiants_valides(configuration: Configuration, identifiant: str, mot_de_passe: str) -> bool:
    # Les deux comparaisons sont toujours faites, à temps constant, pour ne pas dire laquelle échoue.
    bon_identifiant = hmac.compare_digest(identifiant.encode(), configuration.identifiant.encode())
    bon_mot_de_passe = hmac.compare_digest(mot_de_passe.encode(), configuration.mot_de_passe.encode())
    return bon_identifiant & bon_mot_de_passe


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def _empreinte_mot_de_passe(jeton: str, mot_de_passe: str) -> str:
    # Clé = le jeton, jamais stocké : lire la base ne permet pas d'attaquer le mot de passe hors ligne.
    return hmac.new(jeton.encode(), mot_de_passe.encode(), hashlib.sha256).hexdigest()


def ouvrir(base: Session, mot_de_passe: str, maintenant: datetime) -> str:
    jeton = secrets.token_urlsafe(32)
    base.add(
        SessionAdministrateur(
            empreinte_jeton=_empreinte(jeton),
            empreinte_mot_de_passe=_empreinte_mot_de_passe(jeton, mot_de_passe),
            cree_le=maintenant,
        )
    )
    base.commit()
    return jeton


def est_valide(base: Session, jeton: str, mot_de_passe: str, maintenant: datetime) -> bool:
    """Session connue, de moins de 24 h (sans prolongation), ouverte avec le mot de passe en vigueur."""
    session = base.get(SessionAdministrateur, _empreinte(jeton))
    return (
        session is not None
        and maintenant < session.cree_le + DUREE
        and hmac.compare_digest(
            session.empreinte_mot_de_passe, _empreinte_mot_de_passe(jeton, mot_de_passe)
        )
    )


def fermer(base: Session, jeton: str) -> None:
    session = base.get(SessionAdministrateur, _empreinte(jeton))
    if session is not None:
        base.delete(session)
        base.commit()
