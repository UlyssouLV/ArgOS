"""Configuration du Site, lue dans l'environnement (`.env` via Docker Compose)."""

from dataclasses import dataclass
from ipaddress import IPv4Network

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
    # API de contrôle de MediaMTX (réseau Compose seulement) et délai de ses réponses, en secondes.
    url_api_mediamtx: str = Field("http://mediamtx:9997", validation_alias="ARGOS_MEDIAMTX_API")
    delai_mediamtx: float = Field(5, gt=0, validation_alias="ARGOS_MEDIAMTX_DELAI_S")
    # Origines exactes (séparées par des virgules) autorisées à appeler l'API avec le cookie de session.
    origines_autorisees: str = Field(
        "http://localhost:8080,http://localhost:5173", validation_alias="ARGOS_ORIGINES_AUTORISEES"
    )

    # Détection des Caméras : sous-réseaux IPv4 (CIDR) et ports sondés, séparés par des virgules.
    # Réglage vide ou invalide : l'API démarre, seule la Détection est indisponible.
    detection_sous_reseaux: str = Field("", validation_alias="ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX")
    detection_ports: str = Field("554,8554", validation_alias="ARGOS_DETECTION_CAMERAS_PORTS")

    def liste_origines_autorisees(self) -> list[str]:
        return [origine.strip() for origine in self.origines_autorisees.split(",") if origine.strip()]

    def reglage_detection(self) -> "ReglageDetection":
        try:
            ports = [int(port) for port in _elements(self.detection_ports)]
        except ValueError:
            ports = []
        if not ports or not all(0 < port < 65536 for port in ports):
            return ReglageDetection([], [], f"{INVALIDE} : ports « {self.detection_ports} » (ex. 554,8554).")
        if not _elements(self.detection_sous_reseaux):
            return ReglageDetection([], ports, NON_CONFIGUREE)
        sous_reseaux = []
        for element in _elements(self.detection_sous_reseaux):
            try:
                sous_reseaux.append(IPv4Network(element, strict=False))
            except ValueError:
                return ReglageDetection(
                    [], ports, f"{INVALIDE} : « {element} » n'est pas un sous-réseau IPv4 (ex. 192.168.1.0/24)."
                )
        return ReglageDetection(sous_reseaux, ports, None)


NON_CONFIGUREE = (
    "Détection non configurée : aucun sous-réseau autorisé (ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX). "
    "Lancer scripts/cameras/configurer-detection.sh sur la machine du Site, puis relancer ArgOS ; "
    "voir docs/cameras/reseau-et-detection.md."
)
INVALIDE = "Configuration de la Détection invalide (ARGOS_DETECTION_CAMERAS_*)"


@dataclass(frozen=True)
class ReglageDetection:
    sous_reseaux: list[IPv4Network]
    ports: list[int]
    # Pourquoi la Détection est indisponible ; `None` : configurée.
    raison: str | None


def _elements(liste: str) -> list[str]:
    return [element.strip() for element in liste.split(",") if element.strip()]


def charger() -> Configuration:
    try:
        return Configuration()
    except ValidationError as erreur:
        variables = sorted({str(e["loc"][0]) for e in erreur.errors()})
        raise ConfigurationIncomplete(
            f"L'API du Site refuse de démarrer : {', '.join(variables)} absente(s), vide(s) ou invalide(s). "
            "Les définir dans .env (voir .env.example) ; il n'existe aucun compte par défaut."
        ) from None
