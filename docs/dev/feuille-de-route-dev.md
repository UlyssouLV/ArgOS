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

## 0.4.0 — Détection des Caméras sur le réseau

**Livrée** ([PR #24](https://github.com/UlyssouLV/ArgOS/pull/24)).

Spec : [v0.4.0](../specs/v0.4.0-detection-des-cameras.md).

Depuis l’Administration, lancer une **Détection** sur le(s) sous-réseau(x) autorisé(s) du Site et afficher la liste des **Candidats** : hôtes qui acceptent une connexion sur un port caméra (`554`, `8554`) et répondent à une requête RTSP `OPTIONS`, sans identifiants. Ceux qui correspondent déjà à une Caméra du Site sont rangés dans « Déjà configurées », repliée. Rien n’est ajouté ni stocké ; ArgOS lui-même n’est jamais Candidat. Détection réservée à une session, une seule à la fois, 1024 adresses au plus.

L’API, dans Docker, ne voit pas les prises de la machine ([ADR 0002](../adr/0002-detection-depuis-le-reseau-bridge.md)) : le script hôte `scripts/cameras/configurer-detection.sh` demande une fois la prise des caméras, puis recalcule à chaque lancement ses sous-réseaux dans `.env`. Les Caméras simulées deviennent trois conteneurs RTSP sur le port 554 (l’un avec identifiants), sur leur propre réseau, déclarés par `compose.simulation.yaml`, absent de la prod. Doc pédagogique : [Réseau du Site et Détection des Caméras](../cameras/reseau-et-detection.md).

La Détection ne lit pas le switch (non géré) : elle voit ce qui est joignable depuis le serveur ArgOS. Entrée manuelle (« appareil non détecté ») hors scope de cette version.

## 0.4.1 — Ajout d’une Caméra depuis un Candidat

**Livrée** ([PR #34](https://github.com/UlyssouLV/ArgOS/pull/34)).

Spec : [v0.4.1](../specs/v0.4.1-ajout-camera-depuis-candidat.md).

Depuis l’Administration, **Ajouter** sur un Candidat : ArgOS cherche seul le Flux en essayant les chemins courants des caméras (flux principal avant secondaire, marque reconnue dans l’en-tête `Server` en tête). Une caméra qui répond `401` fait demander identifiant (`admin` prérempli) et mot de passe, un seul essai par clic ; aucun chemin courant ne répond : l’Administrateur saisit le chemin. Le Flux trouvé s’affiche en **Aperçu** dans l’Administration (chemin MediaMTX éphémère `apercu-*`, un seul à la fois, jamais dans le Live), avec nom et emplacement à remplir, puis « Ajouter la Caméra ». Un codec que le navigateur ne lit pas (H.265) est nommé, sans empêcher l’ajout.

**Ajouter par adresse IP** couvre l’appareil non détecté, par le même parcours ; l’Administration n’offre plus d’ajout par URL RTSP (la modification reste). Essai réservé à une session, un à la fois, réseau local seulement. Les Caméras simulées servent des chemins de vraies caméras (Hikvision, Dahua avec identifiants, exotique). Doc : [Ajouter une Caméra](../cameras/ajouter-une-camera.md).

## 0.4.2 — Identité stable par adresse MAC

Conserver en base l’**adresse MAC** de chaque Caméra (quand elle est connue à la détection ou à l’ajout) pour la reconnaître si son IP change (DHCP), mettre à jour l’URL RTSP en conséquence, et éviter de traiter le même appareil physique comme une nouvelle Caméra.

Ajout manuel par adresse MAC : à côté de **Ajouter par adresse IP**, saisir la MAC d’un appareil (lue sur son étiquette) pour l’ajouter par le même parcours.

## 1.0.0 — Fil rouge Site → Live RTSP

**À redéfinir** : la vidéo arrive en 0.3.0.

Relier bout en bout login, caméras du Site et Live sur les flux RTSP (simulés) pour qu’un utilisateur voie réellement la vidéo et puisse enchaîner les caméras.

## Plus tard — Configuration initiale du Site

Régler depuis l’Administration, au premier lancement, ce qui vit aujourd’hui dans `.env` : sous-réseaux et ports de la Détection des Caméras, origines autorisées de l’UI, etc.

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

Rendre lisibles dans le Live et l’Aperçu les Caméras qui n’émettent pas du H.264 (H.265 notamment), malgré le support navigateur inégal : **réencodage** en H.264 côté serveur (coûteux en calcul), ou **un autre transport que WebRTC** (HLS / fMP4, lu par les navigateurs qui décodent le H.265). Depuis la 0.4.1, une telle Caméra s’ajoute déjà et est sondée, mais le navigateur ne l’affiche pas.

## Plus tard — Incrustation nom/heure sur les Caméras simulées

Incruster le nom de la Caméra et l’heure dans l’image des Caméras simulées pour repérer d’un coup d’œil laquelle on regarde et qu’elle n’est pas figée.

## Plus tard — Détection IA

Personnes / véhicules sur substream, après le cœur live.

## Plus tard — ONVIF et PTZ

Au-delà de la détection RTSP (0.4.x) : profils média ONVIF, capacités, pilotage PTZ et tracking éventuel.
