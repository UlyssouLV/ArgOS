"""Connexion de l'Administrateur : vérification des identifiants et sessions en base."""

import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from argos_api.configuration import Configuration
from argos_api.modeles import SessionAdministrateur


def identifiants_valides(configuration: Configuration, identifiant: str, mot_de_passe: str) -> bool:
    # Les deux comparaisons sont toujours faites, à temps constant, pour ne pas dire laquelle échoue.
    bon_identifiant = hmac.compare_digest(identifiant.encode(), configuration.identifiant.encode())
    bon_mot_de_passe = hmac.compare_digest(mot_de_passe.encode(), configuration.mot_de_passe.encode())
    return bon_identifiant & bon_mot_de_passe


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def ouvrir(base: Session) -> str:
    jeton = secrets.token_urlsafe(32)
    base.add(SessionAdministrateur(empreinte_jeton=_empreinte(jeton)))
    base.commit()
    return jeton


def est_valide(base: Session, jeton: str) -> bool:
    return base.get(SessionAdministrateur, _empreinte(jeton)) is not None


def fermer(base: Session, jeton: str) -> None:
    session = base.get(SessionAdministrateur, _empreinte(jeton))
    if session is not None:
        base.delete(session)
        base.commit()
