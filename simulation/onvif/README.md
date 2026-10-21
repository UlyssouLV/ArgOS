# Simulation ONVIF

Fichiers de **dev**, utilisés seulement par `compose.simulation.yaml` (jamais par la stack de prod).

## Pourquoi ce dossier

Les Réglages de la Caméra (Incrustations, Horloge, Image, Encodage) passent par ONVIF, en HTTPS quand la caméra le propose, en clair seulement avec l'accord de l'Administrateur (`docs/adr/0007-onvif-en-https-par-cle-memorisee.md`). Pour les développer et les tester sans matériel, certaines Caméras simulées répondent en ONVIF comme de vraies caméras. MediaMTX ([`media/simulated/`](../../media/simulated/README.md)) ne sait que diffuser la vidéo : l'interface ONVIF est ce petit service SOAP, lancé à côté de chaque Caméra simulée qui en a une.

`camera_onvif.py`, en bibliothèque standard Python, implémente **seulement** les opérations dont ArgOS se sert :

- appareil (`/onvif/device_service`) : `GetSystemDateAndTime`, `SetSystemDateAndTime`, `GetNTP`, `SetNTP`, `GetCapabilities`, qui annonce l'adresse du service média (et du service image), et `GetServices`, qui annonce chaque service, média 2 compris ;
- média (`/onvif/media_service`) : `GetProfiles`, `GetOSDs`, `GetOSDOptions`, `SetOSD`, `CreateOSD`, `DeleteOSD`, et pour l'Encodage (le repli d'une caméra sans média 2) `GetStreamUri`, `GetVideoEncoderConfigurations`, `GetVideoEncoderConfigurationOptions`, `SetVideoEncoderConfiguration` ;
- image (`/onvif/imaging_service`, seulement avec `ONVIF_SERVICES=…image…`) : `GetImagingSettings`, `GetOptions`, `SetImagingSettings` ;
- média 2 (`/onvif/media2_service`, seulement avec `ONVIF_SERVICES=…media2…`) : `GetProfiles`, `GetStreamUri`, `GetVideoEncoderConfigurations`, `GetVideoEncoderConfigurationOptions`, `SetVideoEncoderConfiguration`.

Toute autre opération reçoit une faute SOAP `ter:ActionNotSupported`. L'état vit en mémoire : chaque démarrage remet la caméra « sortie d'usine », comme la caméra de dev XiongMai (sauf l'horloge) :

- Horloge en avance de 7 minutes sur l'heure réelle, en mode manuel, fuseau `AWST-8`, serveur NTP `NTP` (un nom qui ne mène nulle part) ;
- une source vidéo (un profil) ;
- Incrustation du nom `CAM01` en haut à gauche, Incrustation de la date et de l'heure (`yyyy-MM-dd HH:mm:ss`) en bas à gauche ;
- `GetOSDOptions` annonce la création des deux types (un de chaque au plus) : une Incrustation cachée (`DeleteOSD`) peut revenir (`CreateOSD`).
- un texte incrusté de plus de 32 caractères est refusé (faute `ter:InvalidArgVal`), comme sur beaucoup de caméras : c'est le cas « réglage refusé » ;
- un profil par chemin RTSP (`ONVIF_CHEMINS_RTSP`, un ou deux, `/Streaming/Channels/101` par défaut) : `mainStream` (`Profile_1`) puis `subStream` (`Profile_2`), sur la même source vidéo, chacun avec son encodeur ; `GetStreamUri` donne `rtsp://<hôte joint><chemin>` ;
- Encodage du flux principal en H.264, 2304×1296 (1920×1080 et 1280×720 proposées), 20 images par seconde (1 à 22), 4096 kbit/s (512 à 8192), qualité 4, GOP 40 ; du flux secondaire 800×448 (640×360, 352×288), 15 images par seconde, 512 kbit/s (64 à 2048), GOP 30. Résolution non proposée, valeur hors bornes ou autre codec : faute `ter:ConfigModify`. Les médias 1 et 2 règlent le même encodeur ; le média 1 décrit toujours le codec en H.264, comme la caméra de dev ;
- Image : filtre infrarouge automatique (`ON` jour, `OFF` nuit, `AUTO`), luminosité, saturation, contraste et netteté à 50 (bornes 0 à 100), contre-jour coupé (`OFF`/`ON`, sans niveau borné : mode seul), WDR coupé (`OFF`/`ON`, niveau 50, borné 0 à 100). Valeur hors bornes ou mode inconnu : faute `ter:InvalidArgVal`, rien n'est changé. Le **WDR** est accepté mais pas appliqué : il reste à sa valeur d'origine, c'est le cas « pas pris ».

Les valeurs envoyées sont retenues en mémoire et relues ; la vidéo simulée, elle, ne change pas (ni résolution, ni image).

`ONVIF_SERVICES` (vide par défaut : appareil et média 1 seuls) ajoute `image` et `media2`, séparés par des virgules. Pour la Caméra simulée 2, compose le lit dans `ONVIF_SERVICES_2` (`image,media2` par défaut) : `ONVIF_SERVICES_2=image` coupe le média 2 au démarrage (ni annoncé, ni servi), pour tester le repli média 1 sur son Flux H.264.

`ONVIF_SILENCE_APRES_ENCODAGE_S` (vide par défaut : jamais) rend la caméra muette ce nombre de secondes après chaque changement d'Encodage accepté (médias 1 et 2) : elle ferme chaque connexion sans répondre, sur tous ses services, comme une caméra qui relance son encodeur. C'est le cas « la caméra n'a pas répondu après l'envoi ». Pour la Caméra simulée 2, compose le lit dans `ONVIF_SILENCE_APRES_ENCODAGE_S_2`.

`ONVIF_PORT_NTP` (`123` par défaut) est le port où la caméra joint ses serveurs NTP. Pour la Caméra simulée 2, compose le lit dans `ONVIF_PORT_NTP_2` : un port où rien ne répond donne une caméra calée sur le Site dont l'horloge garde son avance, le cas « écart » de la vérification des Caméras.

`ONVIF_NTP_PARESSEUX` (vide par défaut : vrai client NTP continu) fait de la caméra une caméra « NTP paresseux », dont le NTP est bien réglé mais qui ne se synchronise pas toute seule : sa valeur est la dérive de son horloge, en secondes par heure (voir [Horloge et serveur de temps](#horloge-et-serveur-de-temps)). Pour la Caméra simulée 5, compose le lit dans `ONVIF_NTP_PARESSEUX_5` (`60` par défaut : une minute par heure) ; les tests l'accélèrent.

`ONVIF_TYPES_CREABLES` (`Plain,DateAndTime` par défaut) restreint les types d'Incrustation que `GetOSDOptions` annonce et que `CreateOSD` accepte : c'est le cas d'une caméra qui ne sait pas réafficher une Incrustation cachée. Pour la Caméra simulée 4, compose le lit dans `ONVIF_TYPES_CREABLES_4`.

## Horloge et serveur de temps

`SetNTP` retient un serveur manuel (`IPv4`, `IPv6` ou `DNS`, le premier reçu) ; `FromDHCP` à `true` est refusé (faute `ter:InvalidArgVal`) : il n'y a pas de DHCP sur le réseau des Caméras simulées. En mode NTP (`SetSystemDateAndTime`), la caméra **interroge vraiment** ce serveur (client SNTP, UDP 123, réponse attendue 2 s) dès qu'elle reçoit le serveur ou le mode, puis toutes les 64 s, et cale son horloge sur l'heure reçue : `GetSystemDateAndTime` relit l'heure corrigée, `GetNTP` le serveur, et le fuseau envoyé est gardé. Serveur injoignable ou nom inconnu : l'horloge reste telle quelle, le service ONVIF continue de répondre. Chaque interrogation est journalisée (`NTP : calée sur 172.30.0.10 (corrigée de -420.012 s)`, `NTP : … injoignable`). En mode manuel, le serveur reçu n'est pas interrogé.

**NTP paresseux** (`ONVIF_NTP_PARESSEUX`) : la caméra n'interroge le serveur reçu qu'une fois après son démarrage et une fois après chaque `SetNTP`, au premier moment où elle est en mode NTP (tout de suite si elle l'est déjà, sinon au passage en mode NTP) ; jamais toutes les 64 s, et un retour en mode NTP sans nouveau `SetNTP` ne l'interroge pas. Son horloge dérive ensuite, en continu, de la vitesse réglée. Elle honore l'heure poussée par `SetSystemDateAndTime` en mode manuel (UTC) : la dérive repart de cette heure-là. `GetSystemDateAndTime` et `GetNTP` rendent mode, serveur et fuseau comme les autres. C'est le cas d'une caméra calée sur le Site qui dérive quand même, que la Mise à l'heure corrige ([ADR 0015](../../docs/adr/0015-mise-a-l-heure-a-chaque-verification.md)).

Dans la stack de dev, les Caméras simulées joignent le Serveur de temps du Site (`temps`) à son IP fixe sur leur réseau, `172.30.0.10` (`compose.simulation.yaml`).

## Date incrustée dans le Flux

Avec `ONVIF_FICHIER_DATE`, le service réécrit dans ce fichier, toutes les 0,2 s, la date et l'heure de la caméra **à son fuseau** (fuseau POSIX lu par la libc, `yyyy-MM-dd HH:mm:ss`), remplacé d'un bloc. Sa Caméra simulée le relit à chaque image et l'incruste en bas à gauche de son Flux ([`media/simulated/diffuser.sh`](../../media/simulated/diffuser.sh)) : la date incrustée suit l'heure corrigée et le fuseau. Seule cette date est dessinée, toujours au même endroit et au même format : les Incrustations réglées en ONVIF (nom, position, format, Incrustation cachée) ne sont pas dessinées.

## HTTP, HTTPS ou les deux

Le service écoute en HTTP sur `ONVIF_PORT`, en HTTPS sur `ONVIF_PORT_HTTPS`, ou les deux (HTTP sur `80` si aucun n'est renseigné) : une seule caméra, même état, mêmes identifiants. En HTTPS, `ONVIF_CERTIFICAT` et `ONVIF_CLE` donnent les chemins du certificat et de sa clé ; s'ils n'existent pas, un certificat auto-signé est créé (`openssl`), puis gardé : la clé ne change que si les fichiers disparaissent. Les tests s'en servent pour lancer une caméra avec une autre clé.

`ONVIF_TLS_MAX` (`1.0` à `1.3`) plafonne la version TLS servie : c'est le cas d'une caméra ancienne, signalée « TLS ancien » par ArgOS. Pour la Caméra simulée 2, compose le lit dans `ONVIF_TLS_MAX_2`.

Pour la Caméra simulée 2, compose lit aussi `ONVIF_PORT_HTTPS_2` (vide : HTTP seulement, une caméra dont HTTPS a disparu) et `ONVIF_CERTIFICAT_2` / `ONVIF_CLE_2` (hors du volume : une autre clé à la même adresse, comme après une remise en usine). `remettre_onvif_en_usine` (`tests/stack_compose.py`) lui rend HTTPS et son certificat habituel.

Chaque requête reçue est journalisée (sortie d'erreur, `docker compose logs`) avec l'IP du client, le schéma et le port, puis l'opération SOAP (`172.30.0.2 https:443 "POST /onvif/device_service HTTP/1.1" 200 - GetSystemDateAndTime`) : les tests y lisent ce que la caméra a reçu, et par où.

`GetCapabilities` annonce toujours ses adresses en `http://`, à l'hôte sous lequel on la joint, même jointe en HTTPS : comme beaucoup de vraies caméras. Le client ne doit en garder que le chemin.

## Identifiants

Avec des identifiants (`ONVIF_IDENTIFIANT`, `ONVIF_MOT_DE_PASSE`), toute opération sauf `GetSystemDateAndTime` exige un WS-Security UsernameToken en empreinte ; sinon, faute `ter:NotAuthorized` (HTTP 400). La date `Created` du jeton n'est pas comparée à l'Horloge : celle de la caméra est fausse au démarrage.

## Pourquoi il ne dépend pas de l'API

Une vraie caméra ne connaît pas ArgOS : la simulation non plus. Rien n'est importé de `api/`, et elle n'en importe rien. Les tests de l'API la joignent comme une caméra du réseau (SOAP sur HTTPS ou HTTP), jamais par son code. Ainsi, une erreur d'ArgOS ne peut pas être masquée par un simulateur qui partagerait ses modèles.

## Dans la stack de dev

`compose.simulation.yaml` lance un service par Caméra simulée ONVIF, qui **partage le réseau** de sa Caméra simulée (`network_mode: service:camera-simulee-N`) : même IP, même MAC, comme l'interface ONVIF d'une vraie caméra. Un volume par caméra (`camera-simulee-N-horloge`) porte le fichier de la date incrustée, de l'interface ONVIF vers le Flux.

| Caméra simulée     | Service ONVIF            | Adresses                                                                                       | Identifiants                              |
|--------------------|--------------------------|------------------------------------------------------------------------------------------------|-------------------------------------------|
| `camera-simulee-1` | aucun                    | —                                                                                              | —                                         |
| `camera-simulee-2` | `camera-simulee-2-onvif` | `https://172.30.0.12/onvif/device_service`, `http://172.30.0.12:8899/onvif/device_service` | `admin` / `argos-simulee` (comme le Flux) |
| `camera-simulee-3` | aucun                    | —                                                                                              | —                                         |
| `camera-simulee-4` | `camera-simulee-4-onvif` | `http://172.30.0.14/onvif/device_service` (HTTP seulement)                                     | aucun                                     |
| `camera-simulee-5` | `camera-simulee-5-onvif` | `http://172.30.0.15/onvif/device_service` (HTTP seulement)                                     | aucun                                     |

La 2 a le service image et le média 2, et deux profils aux chemins de son URL RTSP (`/cam/realmonitor?channel=1&subtype=0` et `subtype=1`). La 4 n'a que le média 1, sans service image, un seul profil (`/Streaming/Channels/101`), et son Flux est en H.265 : c'est le cas « Image non réglable » et « Encodage non réglable ». La 5 est comme la 4 (HTTP seulement, sans identifiants, média 1 seul), en H.264, et « NTP paresseux » : calée sur `temps`, elle dérive d'une minute par heure jusqu'à la prochaine Mise à l'heure.

Les Caméras simulées 1 et 3 ne répondent pas en ONVIF : c'est le cas « caméra sans ONVIF ». La 2 répond en HTTPS sur `443` et garde HTTP sur `8899`, le port des caméras XiongMai, comme beaucoup de vraies caméras ; son certificat auto-signé est créé au premier démarrage dans le volume `camera-simulee-2-onvif-certificat`, et reste le même ensuite (`docker volume rm` en fait créer un nouveau). La 4 ne propose pas HTTPS.

## Tests

Test-root `simulation/onvif/` (`agents/roles.yml`), lancée par `/t` :

```bash
# depuis simulation/onvif/
uv sync
.venv/bin/python -m pytest
```

Les tests lancent le service dans le processus et l'interrogent en SOAP par HTTP ou HTTPS : réponses aux opérations, état modifié puis relu (WDR non appliqué), refus sans bons identifiants, état « usine » au démarrage, même caméra en HTTPS et en HTTP, calage sur un petit serveur NTP de test (port libre à la place de 123) ou serveur injoignable, caméra « NTP paresseux » (dérive sans nouvelle interrogation, heure poussée gardée), date incrustée. `tests/flux/` vérifie le calage sur `temps` dans la stack. Ceux du lancement par variables d'environnement (HTTPS seul, HTTP seul, les deux ; certificat gardé d'un démarrage à l'autre ; services et profils, média 2 coupé ; silence après un changement d'Encodage ; fichier de la date incrustée) lancent `camera_onvif.py` comme le conteneur.

## Plus tard

Ce dossier est prévu pour rejoindre un futur service ou conteneur de dev qui regrouperait les simulations (Caméras simulées, ONVIF, autres protocoles). Sa structure n'est pas figée : il est autonome (code, `Dockerfile`, tests, `pyproject.toml` des tests) pour pouvoir y être déplacé tel quel.
