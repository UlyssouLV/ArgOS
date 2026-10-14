"""Client ONVIF du Site : lit et modifie les Réglages de la Caméra (Horloge de son Appareil, Incrustations).

L'appelant donne l'URL RTSP de la Caméra et le port ONVIF retenu ; il reçoit les Réglages lus (ou, après une
modification, le résultat de chaque champ envoyé ; après une mise à l'heure, l'Horloge relue) et le port qui a
répondu, ou une `ErreurOnvif` avec son code.
SOAP, recherche du port, profils et tokens restent ici.

- Port : celui retenu s'il répond encore en SOAP, sinon recherche sur les ports courants, dans leur ordre.
- Identifiants : ceux de l'URL RTSP, en WS-Security (empreinte) ; aucun si l'URL n'en a pas.
- Incrustations : celles de la première source vidéo (premier profil média).
- Horloge : le fuseau part seul, en gardant le mode et l'heure de la caméra ; la mise à l'heure du Site passe la
  caméra en mode manuel, à l'heure UTC du serveur, en gardant son fuseau. Jamais de NTP réglé, jamais d'écriture
  sans une demande de l'Administrateur.
- Modification : chaque `Set…` part seul (un refus n'empêche pas les autres), puis la caméra est relue : un champ
  est `pris` si la valeur relue est celle demandée, `pas_pris` sinon, `refuse` si la caméra (ou ArgOS, quand
  elle n'annonce pas savoir recréer une Incrustation) l'a refusé.

WSDL ONVIF d'`onvif-zeep` (licence MIT, `wsdl/LICENSE`), lus par `zeep` : `onvif-zeep` n'est publié qu'en
sources, et l'image de l'API n'installe que des roues.
"""

import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

import requests
import zeep
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from zeep.exceptions import Error as ErreurZeep
from zeep.exceptions import Fault, TransportError
from zeep.transports import Transport
from zeep.wsdl import Document
from zeep.wsse.username import UsernameToken

from argos_api import fuseaux

# Ports ONVIF courants, dans l'ordre de recherche : 8899 est celui des caméras XiongMai.
PORTS_ONVIF = (80, 8899, 2000, 8000, 8080)
CHEMIN_APPAREIL = "/onvif/device_service"
# Délais courts : une caméra du réseau local répond vite, ou ne répondra pas.
DELAI_CONNEXION_S = 2
DELAI_REPONSE_S = 4

DOSSIER_WSDL = Path(__file__).parent / "wsdl"
SOAP_12 = "http://www.w3.org/2003/05/soap-envelope"
SOAP_11 = "http://schemas.xmlsoap.org/soap/envelope/"
DEMANDE_HEURE = (
    f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="{SOAP_12}"><s:Body>'
    '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>'
).encode()

journal = logging.getLogger("argos_api.onvif")

CodeErreur = Literal["sans_onvif", "identifiants_refuses", "injoignable"]
Coin = Literal["UpperLeft", "UpperRight", "LowerLeft", "LowerRight"]
Position = Coin | Literal["Custom"]
CleIncrustation = Literal["nom", "date_heure"]
StatutChamp = Literal["pris", "pas_pris", "refuse"]
# Type de texte ONVIF de chaque Incrustation, et son coin quand ArgOS la réaffiche sans coin demandé.
TYPES_TEXTE: dict[CleIncrustation, str] = {"nom": "Plain", "date_heure": "DateAndTime"}
COINS_PAR_DEFAUT: dict[CleIncrustation, Coin] = {"nom": "UpperLeft", "date_heure": "LowerLeft"}


class ErreurOnvif(Exception):
    def __init__(self, code: CodeErreur) -> None:
        super().__init__(code)
        self.code = code


class Horloge(BaseModel):
    # Date et heure UTC de la caméra, et son écart avec l'heure du Site (positif : la caméra avance).
    date_heure_utc: datetime
    ecart_s: float
    # Fuseau tel que la caméra le donne (POSIX), et son nom IANA s'il est reconnu.
    fuseau_posix: str | None
    fuseau: str | None
    mode: Literal["manuel", "ntp"]
    serveur_ntp: str | None


class IncrustationNom(BaseModel):
    affichee: bool
    texte: str | None
    position: Position | None
    # La caméra annonce savoir recréer cette Incrustation (`GetOSDOptions`).
    peut_etre_reaffichee: bool


class IncrustationDateHeure(BaseModel):
    affichee: bool
    format: str | None
    position: Position | None
    peut_etre_reaffichee: bool


class Incrustations(BaseModel):
    nom: IncrustationNom
    date_heure: IncrustationDateHeure


class Reglages(BaseModel):
    horloge: Horloge
    incrustations: Incrustations


class _ModificationIncrustation(BaseModel):
    """Champs modifiés d'une Incrustation ; un champ absent (ou `null`) n'est pas envoyé."""

    model_config = ConfigDict(extra="forbid")

    affichee: bool | None = None
    position: Coin | None = None

    @model_validator(mode="after")
    def _cacher_seule(self) -> "_ModificationIncrustation":
        # Une Incrustation cachée n'a plus ni texte ni coin : rien d'autre à régler en même temps.
        if self.affichee is False and len(self.model_dump(exclude_none=True)) > 1:
            raise ValueError("Cacher une Incrustation ne se combine avec aucun autre champ de celle-ci")
        return self


class ModificationNom(_ModificationIncrustation):
    texte: str | None = None


class ModificationDateHeure(_ModificationIncrustation):
    """Le format de la date et heure ne s'envoie jamais : les caméras ne le règlent pas de façon fiable."""


class ModificationIncrustations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: ModificationNom | None = None
    date_heure: ModificationDateHeure | None = None


class ModificationHorloge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Nom IANA (`Europe/Paris`) : ArgOS l'envoie en POSIX.
    fuseau: str | None = None

    @field_validator("fuseau")
    @classmethod
    def _fuseau_connu(cls, fuseau: str | None) -> str | None:
        if fuseau is not None and not fuseaux.connu(fuseau):
            raise ValueError("Fuseau IANA inconnu")
        return fuseau


class ModificationReglages(BaseModel):
    """Seulement les champs que l'Administrateur a modifiés."""

    model_config = ConfigDict(extra="forbid")

    horloge: ModificationHorloge = ModificationHorloge()
    incrustations: ModificationIncrustations = ModificationIncrustations()


class ChampModifie(BaseModel):
    # Chemin du champ envoyé : `horloge.fuseau`, `incrustations.nom.texte`…
    champ: str
    demande: str | bool
    # Valeur relue sur la caméra après l'envoi (fuseau : sa chaîne POSIX) ; `None` : sans valeur (Incrustation
    # cachée, caméra sans fuseau).
    relu: str | bool | None
    statut: StatutChamp


class ResultatModification(BaseModel):
    # Seulement les champs envoyés.
    champs: list[ChampModifie]
    # Réglages relus après l'envoi.
    reglages: Reglages


def lire_reglages(
    url_rtsp: str, port_retenu: int | None, maintenant: Callable[[], datetime]
) -> tuple[Reglages, int]:
    """Réglages lus sur la caméra de `url_rtsp`, et port ONVIF qui a répondu. Lève `ErreurOnvif`."""
    camera, port = _joindre(url_rtsp, port_retenu)
    with _erreurs_onvif():
        return camera.lire(maintenant), port


def modifier_reglages(
    url_rtsp: str, port_retenu: int | None, modification: ModificationReglages, maintenant: Callable[[], datetime]
) -> tuple[ResultatModification, int]:
    """Envoie chaque champ de `modification` à la caméra, la relit, et dit si chacun a été pris. Lève `ErreurOnvif`."""
    camera, port = _joindre(url_rtsp, port_retenu)
    with _erreurs_onvif():
        return camera.modifier(modification, maintenant), port


def mettre_a_l_heure(
    url_rtsp: str, port_retenu: int | None, maintenant: Callable[[], datetime]
) -> tuple[Horloge, int]:
    """Met la caméra à l'heure du Site (mode manuel, fuseau gardé), puis relit son Horloge. Lève `ErreurOnvif`."""
    camera, port = _joindre(url_rtsp, port_retenu)
    with _erreurs_onvif():
        return camera.mettre_a_l_heure(maintenant), port


def _joindre(url_rtsp: str, port_retenu: int | None) -> tuple["_Camera", int]:
    morceaux = urlsplit(url_rtsp)
    hote = morceaux.hostname or ""
    identifiants = (unquote(morceaux.username), unquote(morceaux.password or "")) if morceaux.username else None
    port = _trouver_port(hote, port_retenu)
    return _Camera(hote, port, identifiants), port


# --- Recherche du port ------------------------------------------------------------------------------------------


class _Sonde(Enum):
    SOAP = "soap"
    # L'hôte répond (connexion refusée, page web…) mais pas en SOAP.
    AUTRE = "autre"
    MUET = "muet"


def _trouver_port(hote: str, port_retenu: int | None) -> int:
    if port_retenu is not None and _sonder(hote, port_retenu) is _Sonde.SOAP:
        return port_retenu
    with ThreadPoolExecutor(len(PORTS_ONVIF)) as sondes:
        resultats = list(sondes.map(lambda port: _sonder(hote, port), PORTS_ONVIF))
    for port, resultat in zip(PORTS_ONVIF, resultats, strict=True):
        if resultat is _Sonde.SOAP:
            return port
    raise ErreurOnvif("sans_onvif" if _Sonde.AUTRE in resultats else "injoignable")


def _sonder(hote: str, port: int) -> _Sonde:
    """`GetSystemDateAndTime` sans identifiants : seule une enveloppe SOAP prouve ONVIF, pas un `200` HTML."""
    try:
        reponse = requests.post(
            f"http://{hote}:{port}{CHEMIN_APPAREIL}",  # NOSONAR : HTTPS vers la caméra en 0.6.3
            data=DEMANDE_HEURE,
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            timeout=(DELAI_CONNEXION_S, DELAI_REPONSE_S),
            allow_redirects=False,
        )
    except requests.ConnectionError as erreur:
        return _Sonde.AUTRE if _connexion_refusee(erreur) else _Sonde.MUET
    except requests.Timeout:
        return _Sonde.MUET
    except requests.RequestException:
        return _Sonde.AUTRE
    try:
        racine = ET.fromstring(reponse.content)
    except ET.ParseError:
        return _Sonde.AUTRE
    return _Sonde.SOAP if racine.tag in (f"{{{SOAP_12}}}Envelope", f"{{{SOAP_11}}}Envelope") else _Sonde.AUTRE


def _connexion_refusee(erreur: BaseException) -> bool:
    """Refus de connexion : l'hôte est là, rien n'écoute sur ce port."""
    vue: set[int] = set()
    cause: BaseException | None = erreur
    while cause is not None and id(cause) not in vue:
        if isinstance(cause, ConnectionRefusedError):
            return True
        vue.add(id(cause))
        cause = cause.__cause__ or cause.__context__ or next(
            (argument for argument in getattr(cause, "args", ()) if isinstance(argument, BaseException)), None
        )
    return False


# --- Lecture ----------------------------------------------------------------------------------------------------


class _JetonDecale(UsernameToken):
    """UsernameToken en empreinte, daté à l'heure de la caméra : certaines refusent un jeton daté de trop loin."""

    def __init__(self, identifiant: str, mot_de_passe: str, decalage: timedelta) -> None:
        super().__init__(identifiant, mot_de_passe, use_digest=True)
        self.decalage = decalage

    def apply(self, envelope: Any, headers: Any) -> Any:
        self.created = datetime.now(UTC) + self.decalage
        try:
            return super().apply(envelope, headers)
        finally:
            self.created = None


@cache
def _wsdl(nom: str) -> Document:
    return Document(str(DOSSIER_WSDL / f"{nom}.wsdl"), Transport(), settings=_reglages_zeep())


def _reglages_zeep() -> zeep.Settings:
    # Caméras peu rigoureuses : un champ manquant ou en trop ne fait pas échouer la lecture.
    return zeep.Settings(strict=False, xml_huge_tree=True)


def _service(wsdl: str, liaison: str, adresse: str, jeton: UsernameToken | None) -> Any:
    transport = Transport(timeout=DELAI_REPONSE_S, operation_timeout=(DELAI_CONNEXION_S, DELAI_REPONSE_S))
    client = zeep.Client(_wsdl(wsdl), wsse=jeton, transport=transport, settings=_reglages_zeep())
    return client.create_service(liaison, adresse)


class _Camera:
    def __init__(self, hote: str, port: int, identifiants: tuple[str, str] | None) -> None:
        self.adresse = f"http://{hote}:{port}{CHEMIN_APPAREIL}"  # NOSONAR : HTTPS vers la caméra en 0.6.3
        self.identifiants = identifiants
        self._appareil: Any = None
        self._media: Any = None
        self._source = ""

    def _connecter(self) -> None:
        """Services appareil et média, jeton daté à l'heure de la caméra, source vidéo : une fois par requête."""
        if self._media is not None:
            return
        appareil = _service("devicemgmt", "{http://www.onvif.org/ver10/device/wsdl}DeviceBinding", self.adresse, None)
        jeton = None
        if self.identifiants is not None:
            decalage = _date_heure_utc(appareil.GetSystemDateAndTime()) - datetime.now(UTC)
            jeton = _JetonDecale(*self.identifiants, decalage=decalage)
        self._appareil = _service(
            "devicemgmt", "{http://www.onvif.org/ver10/device/wsdl}DeviceBinding", self.adresse, jeton
        )
        adresse_media = self._appareil.GetCapabilities(Category="Media").Media.XAddr
        self._media = _service("media", "{http://www.onvif.org/ver10/media/wsdl}MediaBinding", adresse_media, jeton)
        self._source = self._media.GetProfiles()[0].VideoSourceConfiguration.token

    def lire(self, maintenant: Callable[[], datetime]) -> Reglages:
        self._connecter()
        options = self._media.GetOSDOptions(ConfigurationToken=self._source).OSDOptions
        return Reglages(horloge=self._horloge(maintenant), incrustations=_incrustations(self._osds(), options))

    def _horloge(self, maintenant: Callable[[], datetime]) -> Horloge:
        heure = self._appareil.GetSystemDateAndTime()
        date_heure_utc = _date_heure_utc(heure)
        ntp = self._appareil.GetNTP()
        fuseau_posix = heure.TimeZone.TZ if heure.TimeZone is not None else None
        return Horloge(
            date_heure_utc=date_heure_utc,
            ecart_s=(date_heure_utc - maintenant()).total_seconds(),
            fuseau_posix=fuseau_posix,
            fuseau=fuseaux.nom_lisible(fuseau_posix) if fuseau_posix else None,
            mode="ntp" if heure.DateTimeType == "NTP" else "manuel",
            serveur_ntp=_serveur_ntp(ntp),
        )

    def mettre_a_l_heure(self, maintenant: Callable[[], datetime]) -> Horloge:
        self._connecter()
        # Un refus se voit à l'écart relu, inchangé.
        self._regler_horloge(heure_du_site=maintenant())
        return self._horloge(maintenant)

    def _regler_horloge(self, *, fuseau_posix: str | None = None, heure_du_site: datetime | None = None) -> bool:
        """`SetSystemDateAndTime` ; ce qui n'est pas demandé reste celui de la caméra. `False` : refusé.

        Sans `heure_du_site`, le mode est gardé et, en manuel, l'heure renvoyée est celle que la caméra vient de
        donner : ONVIF l'exige en mode manuel.
        """
        heure = self._appareil.GetSystemDateAndTime()
        manuel = heure_du_site is not None or heure.DateTimeType != "NTP"
        arguments: dict[str, Any] = {
            "DateTimeType": "Manual" if manuel else "NTP",
            "DaylightSavings": bool(heure.DaylightSavings),
        }
        fuseau = fuseau_posix or (heure.TimeZone.TZ if heure.TimeZone is not None else None)
        if fuseau:
            arguments["TimeZone"] = {"TZ": fuseau}
        if manuel:
            utc = (heure_du_site or _date_heure_utc(heure)).astimezone(UTC)
            arguments["UTCDateTime"] = {
                "Date": {"Year": utc.year, "Month": utc.month, "Day": utc.day},
                "Time": {"Hour": utc.hour, "Minute": utc.minute, "Second": utc.second},
            }
        return self._envoyer(self._appareil.SetSystemDateAndTime, **arguments)

    def modifier(self, modification: ModificationReglages, maintenant: Callable[[], datetime]) -> ResultatModification:
        avant = self.lire(maintenant).incrustations
        fuseau = modification.horloge.fuseau
        fuseau_refuse = fuseau is not None and not self._regler_horloge(fuseau_posix=fuseaux.posix(fuseau))
        envois: list[tuple[CleIncrustation, dict[str, Any], set[str]]] = []
        for cle in TYPES_TEXTE:
            changement = getattr(modification.incrustations, cle)
            if changement is None:
                continue
            envoyes = changement.model_dump(exclude_none=True)
            if envoyes:
                envois.append((cle, envoyes, self._modifier_incrustation(cle, envoyes, getattr(avant, cle))))
        apres = self.lire(maintenant)
        champs = []
        if fuseau is not None:
            relu = apres.horloge.fuseau_posix
            statut = _statut(fuseau_refuse, relu, fuseaux.posix(fuseau))
            champs.append(ChampModifie(champ="horloge.fuseau", demande=fuseau, relu=relu, statut=statut))
        for cle, envoyes, refuses in envois:
            relue = getattr(apres.incrustations, cle)
            for champ, demande in envoyes.items():
                relu = getattr(relue, champ)
                statut = _statut(champ in refuses, relu, demande)
                champs.append(
                    ChampModifie(champ=f"incrustations.{cle}.{champ}", demande=demande, relu=relu, statut=statut)
                )
        return ResultatModification(champs=champs, reglages=apres)

    def _modifier_incrustation(
        self, cle: CleIncrustation, envoyes: dict[str, Any], lue: IncrustationNom | IncrustationDateHeure
    ) -> set[str]:
        """Envoie les champs d'une Incrustation ; rend ceux qui ont été refusés."""
        if envoyes.get("affichee") is False:
            return self._cacher_incrustation(TYPES_TEXTE[cle])
        if not lue.affichee:
            return self._reafficher_incrustation(cle, envoyes, lue.peut_etre_reaffichee)
        return self._changer_incrustation(TYPES_TEXTE[cle], envoyes)

    def _cacher_incrustation(self, type_texte: str) -> set[str]:
        osd = self._osd(type_texte)
        return set() if osd is None or self._envoyer(self._media.DeleteOSD, OSDToken=osd.token) else {"affichee"}

    def _reafficher_incrustation(
        self, cle: CleIncrustation, envoyes: dict[str, Any], peut_etre_reaffichee: bool
    ) -> set[str]:
        # Seule une création la fait revenir, avec son texte et son coin : sans annonce, rien n'est envoyé.
        if envoyes.get("affichee") is not True or not peut_etre_reaffichee:
            return set(envoyes)
        type_texte = TYPES_TEXTE[cle]
        texte = {"PlainText": envoyes.get("texte", "")} if type_texte == "Plain" else {}
        osd = {
            "token": "",
            "VideoSourceConfigurationToken": self._source,
            "Type": "Text",
            "Position": {"Type": envoyes.get("position", COINS_PAR_DEFAUT[cle])},
            "TextString": {"Type": type_texte, **texte},
        }
        return set() if self._envoyer(self._media.CreateOSD, OSD=osd) else set(envoyes)

    def _changer_incrustation(self, type_texte: str, envoyes: dict[str, Any]) -> set[str]:
        refuses = set()
        # Un `SetOSD` par champ, sur l'Incrustation relue à chaque fois : un refus ne fausse pas le suivant.
        for champ in ("texte", "position"):
            if champ not in envoyes:
                continue
            osd = self._osd(type_texte)
            if osd is None:
                refuses.add(champ)
                continue
            if champ == "texte":
                osd.TextString.PlainText = envoyes["texte"]
            else:
                # Un coin remplace une position personnalisée et ses coordonnées.
                osd.Position.Type = envoyes["position"]
                osd.Position.Pos = None
            if not self._envoyer(self._media.SetOSD, OSD=osd):
                refuses.add(champ)
        return refuses

    def _envoyer(self, operation: Callable[..., Any], **arguments: Any) -> bool:
        """`False` si la caméra refuse (faute SOAP autre qu'un refus d'identifiants)."""
        try:
            operation(**arguments)
        except Fault as faute:
            if _identifiants_refuses(faute):
                raise
            journal.info("ONVIF : réglage refusé par la caméra : %s", faute.message)
            return False
        return True

    def _osds(self) -> list[Any]:
        return self._media.GetOSDs(ConfigurationToken=self._source) or []

    def _osd(self, type_texte: str) -> Any:
        return _textes(self._osds()).get(type_texte)


def _statut(refuse: bool, relu: object, demande: object) -> StatutChamp:
    """`refuse` si la caméra a refusé l'envoi ; sinon `pris` si la valeur relue est celle demandée."""
    if refuse:
        return "refuse"
    return "pris" if relu == demande else "pas_pris"


def _date_heure_utc(heure: Any) -> datetime:
    utc = heure.UTCDateTime
    return datetime(
        utc.Date.Year, utc.Date.Month, utc.Date.Day, utc.Time.Hour, utc.Time.Minute, utc.Time.Second, tzinfo=UTC
    )


def _serveur_ntp(ntp: Any) -> str | None:
    serveurs = (ntp.NTPFromDHCP if ntp.FromDHCP else ntp.NTPManual) or []
    for serveur in serveurs:
        nom = {"DNS": serveur.DNSname, "IPv4": serveur.IPv4Address, "IPv6": serveur.IPv6Address}.get(serveur.Type)
        if nom:
            return nom
    return None


def _textes(osds: list[Any]) -> dict[str, Any]:
    """Première Incrustation de texte de chaque type : `Plain` (le nom), `DateAndTime` (la date et heure)."""
    textes: dict[str, Any] = {}
    for osd in osds:
        if osd.TextString is None:
            continue
        type_texte = "DateAndTime" if osd.TextString.Type in ("DateAndTime", "Date", "Time") else osd.TextString.Type
        textes.setdefault(type_texte, osd)
    return textes


def _incrustations(osds: list[Any], options: Any) -> Incrustations:
    textes = _textes(osds)
    nom, date_heure = textes.get("Plain"), textes.get("DateAndTime")
    creables = set(options.TextOption.Type or []) if options.TextOption is not None else set()
    return Incrustations(
        nom=IncrustationNom(
            affichee=nom is not None,
            texte=nom.TextString.PlainText if nom else None,
            position=_position(nom),
            peut_etre_reaffichee="Plain" in creables,
        ),
        date_heure=IncrustationDateHeure(
            affichee=date_heure is not None,
            format=_format(date_heure),
            position=_position(date_heure),
            peut_etre_reaffichee="DateAndTime" in creables,
        ),
    )


def _position(osd: Any) -> Position | None:
    if osd is None:
        return None
    position = osd.Position.Type
    return position if position in ("UpperLeft", "UpperRight", "LowerLeft", "LowerRight") else "Custom"


def _format(osd: Any) -> str | None:
    if osd is None:
        return None
    return " ".join(f for f in (osd.TextString.DateFormat, osd.TextString.TimeFormat) if f) or None


# --- Erreurs ----------------------------------------------------------------------------------------------------


@contextmanager
def _erreurs_onvif() -> Iterator[None]:
    """Traduit les erreurs de zeep et du réseau en codes : la caméra a pu cesser de répondre en cours de lecture."""
    try:
        yield
    except (requests.ConnectionError, requests.Timeout) as erreur:
        raise ErreurOnvif("injoignable") from erreur
    except (ErreurZeep, requests.RequestException, AttributeError, IndexError, TypeError, ValueError) as erreur:
        if _identifiants_refuses(erreur):
            raise ErreurOnvif("identifiants_refuses") from erreur
        # Réponse inattendue (faute, champ absent) : la caméra ne répond pas en ONVIF comme ArgOS l'attend.
        journal.warning("ONVIF : réponse inattendue : %r", erreur)
        raise ErreurOnvif("sans_onvif") from erreur


def _identifiants_refuses(erreur: BaseException) -> bool:
    if isinstance(erreur, TransportError):
        return erreur.status_code in (401, 403)
    if isinstance(erreur, Fault):
        texte = " ".join(str(morceau) for morceau in (erreur.message, erreur.code, *(erreur.subcodes or [])))
        return "notauthorized" in texte.lower().replace(" ", "")
    return False
