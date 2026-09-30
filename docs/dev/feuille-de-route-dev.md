# Feuille de route de dev

Vers une **1.0.0** rudimentaire : connexion à un **Site**, onglets **Administration** (CRUD caméras, infos, états) et **Live** (une caméra en grand, bouton suivant). Pas d’enregistrement, pas d’IA, pas d’ONVIF dans ce périmètre.

Contraintes transverses :

- Chaque version a des **exigences écrites** dans les tickets / projet GitHub à l’ouverture de version.
- README type repos Ulysse : sections claires (**quoi**, **prérequis**, **comment lancer**, structure) — enrichi dès qu’une version devient lançable ; avant ça, pas de fausse « souche » runnable.
- Preuve 0.1.0 : flux RTSP simulés **joignables**, y compris un accès **navigateur** (ex. page HLS/WebRTC MediaMTX), plus tests auto (`ffprobe` / équivalent) via `/t`.
- Auth 1.0.0 : compte **local** suffit. États caméra minimaux : `unknown` / `online` / `offline`.

## 0.1.0 — Flux RTSP simulés

Rendre disponibles un ou plusieurs flux RTSP de test via MediaMTX (et source vidéo en boucle), vérifiables en CLI et dans le navigateur, avec tests automatisés qui échouent si le tuyau est cassé.

## 0.2.0 — API Site, auth et caméras

Exposer l’API d’un Site avec authentification locale, CRUD caméras (nom, URL RTSP, infos réseau) et lecture d’état `unknown` / `online` / `offline`.

## 0.3.0 — UI login, Admin et Live

Livrer le frontend React : connexion, onglet Administration (gérer les caméras) et onglet Live (une image en grand, navigation vers la caméra suivante), branché sur l’API.

## 1.0.0 — Fil rouge Site → Live RTSP

Relier bout en bout login, caméras du Site et Live sur les flux RTSP (simulés) pour qu’un utilisateur voie réellement la vidéo et puisse enchaîner les caméras.

## Plus tard — Enregistrement sans réencodage

Conserver les flux utiles sur disque, hors scope 1.0.0.

## Plus tard — Codecs multiples (H.265…)

Accepter des Caméras qui n’émettent pas du H.264 (H.265 notamment) et les rendre lisibles dans le Live malgré le support navigateur inégal.

## Plus tard — Incrustation nom/heure sur les Caméras simulées

Incruster le nom de la Caméra et l’heure dans l’image des Caméras simulées pour repérer d’un coup d’œil laquelle on regarde et qu’elle n’est pas figée.

## Plus tard — Détection IA

Personnes / véhicules sur substream, après le cœur live.

## Plus tard — ONVIF et PTZ

Découverte, capacités, pilotage et tracking éventuel.
