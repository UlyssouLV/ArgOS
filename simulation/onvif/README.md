# Simulation ONVIF

Fichiers de **dev**, utilisés seulement par `compose.simulation.yaml` (jamais par la stack de prod).

## Pourquoi ce dossier

Les Réglages de la Caméra (Incrustations, Horloge) passent par ONVIF, en HTTPS quand la caméra le propose, en clair seulement avec l'accord de l'Administrateur (`docs/adr/0007-onvif-en-https-par-cle-memorisee.md`). Pour les développer et les tester sans matériel, certaines Caméras simulées répondent en ONVIF comme de vraies caméras. MediaMTX ([`media/simulated/`](../../media/simulated/README.md)) ne sait que diffuser la vidéo : l'interface ONVIF est ce petit service SOAP, lancé à côté de chaque Caméra simulée qui en a une.

`camera_onvif.py`, en bibliothèque standard Python, implémente **seulement** les opérations dont ArgOS se sert :

- appareil (`/onvif/device_service`) : `GetSystemDateAndTime`, `SetSystemDateAndTime`, `GetNTP`, et `GetCapabilities`, qui annonce l'adresse du service média ;
- média (`/onvif/media_service`) : `GetProfiles`, `GetOSDs`, `GetOSDOptions`, `SetOSD`, `CreateOSD`, `DeleteOSD`.

Toute autre opération reçoit une faute SOAP `ter:ActionNotSupported`. L'état vit en mémoire : chaque démarrage remet la caméra « sortie d'usine », comme la caméra de dev XiongMai :

- Horloge au 31/12/1999 (UTC), en mode manuel, fuseau `AWST-8`, serveur NTP `NTP` ;
- une source vidéo (un profil) ;
- Incrustation du nom `CAM01` en haut à gauche, Incrustation de la date et de l'heure (`yyyy-MM-dd HH:mm:ss`) en bas à gauche ;
- `GetOSDOptions` annonce la création des deux types (un de chaque au plus) : une Incrustation cachée (`DeleteOSD`) peut revenir (`CreateOSD`).
- un texte incrusté de plus de 32 caractères est refusé (faute `ter:InvalidArgVal`), comme sur beaucoup de caméras : c'est le cas « réglage refusé ».

`ONVIF_TYPES_CREABLES` (`Plain,DateAndTime` par défaut) restreint les types d'Incrustation que `GetOSDOptions` annonce et que `CreateOSD` accepte : c'est le cas d'une caméra qui ne sait pas réafficher une Incrustation cachée. Pour la Caméra simulée 4, compose le lit dans `ONVIF_TYPES_CREABLES_4`.

## HTTP, HTTPS ou les deux

Le service écoute en HTTP sur `ONVIF_PORT`, en HTTPS sur `ONVIF_PORT_HTTPS`, ou les deux (HTTP sur `80` si aucun n'est renseigné) : une seule caméra, même état, mêmes identifiants. En HTTPS, `ONVIF_CERTIFICAT` et `ONVIF_CLE` donnent les chemins du certificat et de sa clé ; s'ils n'existent pas, un certificat auto-signé est créé (`openssl`), puis gardé : la clé ne change que si les fichiers disparaissent. Les tests s'en servent pour lancer une caméra avec une autre clé.

`ONVIF_TLS_MAX` (`1.0` à `1.3`) plafonne la version TLS servie : c'est le cas d'une caméra ancienne, signalée « TLS ancien » par ArgOS. Pour la Caméra simulée 2, compose le lit dans `ONVIF_TLS_MAX_2`.

Pour la Caméra simulée 2, compose lit aussi `ONVIF_PORT_HTTPS_2` (vide : HTTP seulement, une caméra dont HTTPS a disparu) et `ONVIF_CERTIFICAT_2` / `ONVIF_CLE_2` (hors du volume : une autre clé à la même adresse, comme après une remise en usine). `remettre_onvif_en_usine` (`tests/stack_compose.py`) lui rend HTTPS et son certificat habituel.

Chaque requête reçue est journalisée (sortie d'erreur, `docker compose logs`) avec l'IP du client, le schéma et le port (`172.30.0.2 https:443 "POST /onvif/device_service HTTP/1.1" 200 -`) : les tests y lisent ce que la caméra a reçu, et par où.

`GetCapabilities` annonce toujours ses adresses en `http://`, à l'hôte sous lequel on la joint, même jointe en HTTPS : comme beaucoup de vraies caméras. Le client ne doit en garder que le chemin.

## Identifiants

Avec des identifiants (`ONVIF_IDENTIFIANT`, `ONVIF_MOT_DE_PASSE`), toute opération sauf `GetSystemDateAndTime` exige un WS-Security UsernameToken en empreinte ; sinon, faute `ter:NotAuthorized` (HTTP 400). La date `Created` du jeton n'est pas comparée à l'Horloge : celle de la caméra est fausse au démarrage. Les Incrustations ne sont pas dessinées dans la vidéo simulée.

## Pourquoi il ne dépend pas de l'API

Une vraie caméra ne connaît pas ArgOS : la simulation non plus. Rien n'est importé de `api/`, et elle n'en importe rien. Les tests de l'API la joignent comme une caméra du réseau (SOAP sur HTTPS ou HTTP), jamais par son code. Ainsi, une erreur d'ArgOS ne peut pas être masquée par un simulateur qui partagerait ses modèles.

## Dans la stack de dev

`compose.simulation.yaml` lance un service par Caméra simulée ONVIF, qui **partage le réseau** de sa Caméra simulée (`network_mode: service:camera-simulee-N`) : même IP, même MAC, comme l'interface ONVIF d'une vraie caméra.

| Caméra simulée     | Service ONVIF            | Adresses                                                                                       | Identifiants                              |
|--------------------|--------------------------|------------------------------------------------------------------------------------------------|-------------------------------------------|
| `camera-simulee-1` | aucun                    | —                                                                                              | —                                         |
| `camera-simulee-2` | `camera-simulee-2-onvif` | `https://172.30.0.12/onvif/device_service`, `http://172.30.0.12:8899/onvif/device_service` | `admin` / `argos-simulee` (comme le Flux) |
| `camera-simulee-3` | aucun                    | —                                                                                              | —                                         |
| `camera-simulee-4` | `camera-simulee-4-onvif` | `http://172.30.0.14/onvif/device_service` (HTTP seulement)                                     | aucun                                     |

Les Caméras simulées 1 et 3 ne répondent pas en ONVIF : c'est le cas « caméra sans ONVIF ». La 2 répond en HTTPS sur `443` et garde HTTP sur `8899`, le port des caméras XiongMai, comme beaucoup de vraies caméras ; son certificat auto-signé est créé au premier démarrage dans le volume `camera-simulee-2-onvif-certificat`, et reste le même ensuite (`docker volume rm` en fait créer un nouveau). La 4 ne propose pas HTTPS.

## Tests

Test-root `simulation/onvif/` (`agents/roles.yml`), lancée par `/t` :

```bash
# depuis simulation/onvif/
uv sync
.venv/bin/python -m pytest
```

Les tests lancent le service dans le processus et l'interrogent en SOAP par HTTP ou HTTPS : réponses aux opérations, état modifié puis relu, refus sans bons identifiants, état « usine » au démarrage, même caméra en HTTPS et en HTTP. Ceux du lancement par variables d'environnement (HTTPS seul, HTTP seul, les deux ; certificat gardé d'un démarrage à l'autre) lancent `camera_onvif.py` comme le conteneur.

## Plus tard

Ce dossier est prévu pour rejoindre un futur service ou conteneur de dev qui regrouperait les simulations (Caméras simulées, ONVIF, autres protocoles). Sa structure n'est pas figée : il est autonome (code, `Dockerfile`, tests, `pyproject.toml` des tests) pour pouvoir y être déplacé tel quel.
