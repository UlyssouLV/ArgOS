"""Configuration du Site, lue dans l'environnement (`.env` via Docker Compose)."""

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings


class ConfigurationIncomplete(RuntimeError):
    """Une variable obligatoire manque : l'API ne démarre pas, il n'existe aucun compte par défaut."""


class Configuration(BaseSettings):
    identifiant: str = Field(min_length=1, validation_alias="ARGOS_IDENTIFIANT")
    mot_de_passe: str = Field(min_length=1, validation_alias="ARGOS_MOT_DE_PASSE")
    url_base: str = Field(validation_alias="ARGOS_URL_BASE")
    # Sonde de l'état des Caméras, en secondes.
    intervalle_sonde: float = Field(10, gt=0, validation_alias="ARGOS_SONDE_INTERVALLE_S")
    delai_sonde: float = Field(5, gt=0, validation_alias="ARGOS_SONDE_DELAI_S")


def charger() -> Configuration:
    try:
        return Configuration()
    except ValidationError as erreur:
        variables = sorted({str(e["loc"][0]) for e in erreur.errors()})
        raise ConfigurationIncomplete(
            f"L'API du Site refuse de démarrer : {', '.join(variables)} absente(s), vide(s) ou invalide(s). "
            "Les définir dans .env (voir .env.example) ; il n'existe aucun compte par défaut."
        ) from None
