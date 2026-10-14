# Simulation ONVIF

Fichiers de **dev**, utilisés seulement par `compose.simulation.yaml` (jamais par la stack de prod).

## Pourquoi ce dossier

Les Réglages de la Caméra (Incrustations, Horloge) passent par ONVIF. Pour les développer et les tester sans matériel, certaines Caméras simulées répondent en ONVIF comme de vraies caméras. MediaMTX ([`media/simulated/`](../../media/simulated/README.md)) ne sait que diffuser la vidéo : l'interface ONVIF est ce petit service SOAP, lancé à côté de chaque Caméra simulée qui en a une.

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

Avec des identifiants (`ONVIF_IDENTIFIANT`, `ONVIF_MOT_DE_PASSE`), toute opération sauf `GetSystemDateAndTime` exige un WS-Security UsernameToken en empreinte ; sinon, faute `ter:NotAuthorized` (HTTP 400). La date `Created` du jeton n'est pas comparée à l'Horloge : celle de la caméra est fausse au démarrage. Les Incrustations ne sont pas dessinées dans la vidéo simulée.

## Pourquoi il ne dépend pas de l'API

Une vraie caméra ne connaît pas ArgOS : la simulation non plus. Rien n'est importé de `api/`, et elle n'en importe rien. Les tests de l'API la joignent comme une caméra du réseau (SOAP sur HTTP), jamais par son code. Ainsi, une erreur d'ArgOS ne peut pas être masquée par un simulateur qui partagerait ses modèles.

## Dans la stack de dev

`compose.simulation.yaml` lance un service par Caméra simulée ONVIF, qui **partage le réseau** de sa Caméra simulée (`network_mode: service:camera-simulee-N`) : même IP, même MAC, comme l'interface ONVIF d'une vraie caméra.

| Caméra simulée     | Service ONVIF            | Adresse                                      | Identifiants                              |
|--------------------|--------------------------|----------------------------------------------|-------------------------------------------|
| `camera-simulee-1` | aucun                    | —                                            | —                                         |
| `camera-simulee-2` | `camera-simulee-2-onvif` | `http://172.30.0.12:8899/onvif/device_service` | `admin` / `argos-simulee` (comme le Flux) |
| `camera-simulee-3` | aucun                    | —                                            | —                                         |
| `camera-simulee-4` | `camera-simulee-4-onvif` | `http://172.30.0.14/onvif/device_service`    | aucun                                     |

Les Caméras simulées 1 et 3 ne répondent pas en ONVIF : c'est le cas « caméra sans ONVIF ». Le port `8899` de la 2 est celui des caméras XiongMai.

## Tests

Test-root `simulation/onvif/` (`agents/roles.yml`), lancée par `/t` :

```bash
# depuis simulation/onvif/
uv sync
.venv/bin/python -m pytest
```

Les tests lancent le service dans le processus et l'interrogent en SOAP par HTTP : réponses aux opérations, état modifié puis relu, refus sans bons identifiants, état « usine » au démarrage.

## Plus tard

Ce dossier est prévu pour rejoindre un futur service ou conteneur de dev qui regrouperait les simulations (Caméras simulées, ONVIF, autres protocoles). Sa structure n'est pas figée : il est autonome (code, `Dockerfile`, tests, `pyproject.toml` des tests) pour pouvoir y être déplacé tel quel.
