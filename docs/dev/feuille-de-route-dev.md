# Feuille de route de dev

Vers une **1.0.0** rudimentaire : connexion à un **Site**, onglets **Administration** (CRUD caméras, infos, états) et **Live** (une caméra en grand, bouton suivant). Pas d’enregistrement, pas d’IA, pas d’ONVIF dans ce périmètre.

Contraintes transverses :

- Chaque version a des **exigences écrites** dans les tickets / projet GitHub à l’ouverture de version.
- README type repos Ulysse : sections claires (**quoi**, **prérequis**, **comment lancer**, structure) — enrichi dès qu’une version devient lançable ; avant ça, pas de fausse « souche » runnable.
- Preuve 0.1.0 : flux RTSP simulés **joignables**, y compris un accès **navigateur** (ex. page HLS/WebRTC MediaMTX), plus tests auto (`ffprobe` / équivalent) via `/t`.
- Auth 1.0.0 : compte **local** suffit. États caméra minimaux : `unknown` / `online` / `offline`.
- **Pas d’installation sur de vraies caméras avant HTTPS et authentification des Flux.** Limites et dettes : [sécurité](../securite.md).

## 0.1.0 — Flux RTSP simulés

**Livrée** ([PR #5](https://github.com/UlyssouLV/ArgOS/pull/5)).

Rendre disponibles un ou plusieurs flux RTSP de test via MediaMTX (et source vidéo en boucle), vérifiables en CLI et dans le navigateur, avec tests automatisés qui échouent si le tuyau est cassé.

## 0.2.0 — API Site, auth et caméras

**Livrée** ([PR #11](https://github.com/UlyssouLV/ArgOS/pull/11)).

Exposer l’API d’un Site avec authentification locale, CRUD caméras (nom, URL RTSP, infos réseau) et lecture d’état `unknown` / `online` / `offline`.

Les identifiants RTSP (dans l’URL) sont stockés **en clair** en base pour l’instant ; l’API les masque dans ses réponses.

## 0.3.0 — UI login, Admin et Live

**Livrée** ([PR #17](https://github.com/UlyssouLV/ArgOS/pull/17)).

Livrer le frontend React (conteneur `web`) branché sur l’API : connexion, onglet **Administration** (gérer les Caméras, voir leur état) et onglet **Live** (le Flux d’une Caméra active en grand, passage à la suivante).

La vidéo arrive dès cette version : le Live lit le Flux en **WebRTC** (client WHEP dans le front), depuis **MediaMTX en pont** : l’API réconcilie les Caméras actives avec des chemins MediaMTX `camera-<id>` qui relaient leur URL RTSP, sans réencodage ([ADR 0001](../adr/0001-mediamtx-en-pont.md)).

## 1.0.0 — Fil rouge Site → Live RTSP

**À redéfinir** : la vidéo arrive en 0.3.0.

Relier bout en bout login, caméras du Site et Live sur les flux RTSP (simulés) pour qu’un utilisateur voie réellement la vidéo et puisse enchaîner les caméras.

## Plus tard — Enregistrement sans réencodage

Conserver les flux utiles sur disque, hors scope 1.0.0.

## Plus tard — Chiffrement des identifiants RTSP

Ne plus stocker en clair le mot de passe des Caméras dans la base.

## Plus tard — HTTPS

Servir l’API et le Live en HTTPS (cookie de session `Secure`), pour que mot de passe et session ne circulent plus en clair sur le réseau local. Avant toute installation sur de vraies caméras.

## Plus tard — Authentification des Flux

Fermer l’accès libre aux Flux côté MediaMTX, pour que regarder une Caméra passe par la connexion d’ArgOS. Avant toute installation sur de vraies caméras.

## Plus tard — Accès distant par VPN

Accéder au Site depuis internet par un VPN (WireGuard, Tailscale…), sans redirection de port ni UPnP.

## Plus tard — Détection de Flux figé ou rejoué

Repérer une Caméra `online` dont l’image est figée ou une boucle injectée (heure incrustée qui n’avance pas, images identiques, événements ONVIF de sabotage).

## Plus tard — Codecs multiples (H.265…)

Accepter des Caméras qui n’émettent pas du H.264 (H.265 notamment) et les rendre lisibles dans le Live malgré le support navigateur inégal.

## Plus tard — Incrustation nom/heure sur les Caméras simulées

Incruster le nom de la Caméra et l’heure dans l’image des Caméras simulées pour repérer d’un coup d’œil laquelle on regarde et qu’elle n’est pas figée.

## Plus tard — Détection IA

Personnes / véhicules sur substream, après le cœur live.

## Plus tard — ONVIF et PTZ

Découverte, capacités, pilotage et tracking éventuel.
