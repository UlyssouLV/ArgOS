"""Configuration du Site, lue dans l'environnement (`.env` via Docker Compose)."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Configuration(BaseSettings):
    identifiant: str = Field(min_length=1, validation_alias="ARGOS_IDENTIFIANT")
    mot_de_passe: str = Field(min_length=1, validation_alias="ARGOS_MOT_DE_PASSE")
    url_base: str = Field(validation_alias="ARGOS_URL_BASE")
