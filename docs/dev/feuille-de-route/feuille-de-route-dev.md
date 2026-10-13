# Feuille de route de dev

Vers une **1.0.0** rudimentaire : connexion à un **Site**, onglets **Administration** (CRUD caméras, infos, états, réglages) et **Live** (une caméra en grand, bouton suivant), serveur installable, enregistrement. Pas d’IA dans ce périmètre.

Contraintes transverses :

- Chaque version a des **exigences écrites** dans les tickets / projet GitHub à l’ouverture de version.
- README type repos Ulysse : sections claires (**quoi**, **prérequis**, **comment lancer**, structure) — enrichi dès qu’une version devient lançable ; avant ça, pas de fausse « souche » runnable.
- Preuve 0.1.0 : flux RTSP simulés **joignables**, y compris un accès **navigateur** (ex. page HLS/WebRTC MediaMTX), plus tests auto (`ffprobe` / équivalent) via `/t`.
- Auth 1.0.0 : compte **local** suffit. États caméra minimaux : `unknown` / `online` / `offline`.
- **Pas d’installation sur de vraies caméras avant HTTPS et authentification des Flux.** Limites et dettes : [sécurité](../securite.md).

## Déjà livré

- **0.1.0** — Flux RTSP simulés : MediaMTX et source en boucle, vérifiables en CLI et dans le navigateur, tests auto si le tuyau est cassé ([PR #5](https://github.com/UlyssouLV/ArgOS/pull/5)).
- **0.2.0** — API Site, auth et caméras : API d’un Site, auth locale, CRUD caméras, états `unknown` / `online` / `offline` ; identifiants RTSP encore en clair en base, masqués dans les réponses API ([PR #11](https://github.com/UlyssouLV/ArgOS/pull/11)).
- **0.3.0** — UI login, Admin et Live : frontend React branché sur l’API ; Live en WebRTC (WHEP) via MediaMTX en pont, chemins `camera-<id>` ([PR #17](https://github.com/UlyssouLV/ArgOS/pull/17), [ADR 0001](../adr/0001-mediamtx-en-pont.md)).
- **0.4.0** — Détection des Caméras sur le réseau : Candidats (ports `554` / `8554`, `OPTIONS` RTSP, sans identifiants) ; script hôte pour les sous-réseaux ([PR #24](https://github.com/UlyssouLV/ArgOS/pull/24), [spec](../specs/v0.4.0-detection-des-cameras.md), [ADR 0002](../adr/0002-detection-depuis-le-reseau-bridge.md)).
- **0.4.1** — Ajout d’une Caméra depuis un Candidat : essai des chemins courants, aperçu, ajout par IP ; plus d’ajout par URL RTSP depuis l’Administration ([PR #34](https://github.com/UlyssouLV/ArgOS/pull/34), [spec](../specs/v0.4.1-ajout-camera-depuis-candidat.md)).
- **0.4.2** — Identité stable par adresse MAC : MAC de l’Appareil, MAJ d’IP, filtre par MAC à la place de l’ajout manuel par MAC ([PR #44](https://github.com/UlyssouLV/ArgOS/pull/44), [spec](../specs/v0.4.2-identite-stable-par-adresse-mac.md), [ADR 0003](../adr/0003-macvlan-sur-la-prise-des-cameras.md)).
- **0.5.0** — Lecture des Flux H.265 sans réencodage : LL-HLS fMP4 pour le HEVC, WebRTC inchangé pour le H.264 ([PR #51](https://github.com/UlyssouLV/ArgOS/pull/51), [spec](../specs/v0.5.0-lecture-flux-h265.md), [ADR 0004](../adr/0004-hls-pour-les-flux-h265.md)).

## Prochaine : 0.6.0 — Paramétrage des Caméras par ONVIF

**Objectif.** Régler depuis l’Administration ce que la caméra incruste dans l’image et son horloge, sans passer par son interface web ni par le cloud du fabricant : texte, position et affichage du nom incrusté et de la date et heure, fuseau et NTP, lus et vérifiés après envoi. Une Caméra simulée répond en ONVIF. Doc : [Paramétrer une Caméra](../cameras/parametrer-une-camera.md).

**Hors périmètre :** image, vidéo et événements ONVIF ; PTZ ; HTTPS et authentification des Flux (versions suivantes).

## Ensuite : 0.6.1 — HTTPS

**Objectif.** Servir l’UI, l’API et le Live en HTTPS (cookie de session `Secure`), pour que mot de passe et session ne circulent plus en clair sur le réseau local.

**Hors périmètre :** authentification des Flux MediaMTX (0.6.2). Préalable, avec 0.6.2, à toute installation sur de vraies caméras.

## Ensuite : 0.6.2 — Authentification des Flux

**Objectif.** Fermer l’accès libre aux Flux côté MediaMTX (WHEP, HLS, RTSP), pour que regarder une Caméra passe par la connexion d’ArgOS.

**Hors périmètre :** images versionnées et compose de prod (0.7.0). Préalable, avec 0.6.1, à toute installation sur de vraies caméras.

## Ensuite : 0.7.0 — Serveur installable sans le dépôt

**Objectif.** Produire des images versionnées du serveur (`api`, `web`, pont) et un compose de prod autonome, pour installer et mettre à jour un Site sans les sources, avec ses réglages dans `.env`.

**Hors périmètre :** CI des PR (0.7.1) et publication au registre (0.7.2).

## Ensuite : 0.7.1 — Intégration continue

**Objectif.** Lancer les tests (`/t`) sur chaque PR dans GitHub Actions, stack Docker comprise, pour qu’une PR rouge ne puisse pas être fusionnée.

**Hors périmètre :** publication des images à chaque release (0.7.2).

## Ensuite : 0.7.2 — Livraison continue

**Objectif.** Publier les images du serveur à chaque release (registre GitHub), avec une procédure d’installation et de mise à jour d’un serveur Linux : on peut installer ArgOS sur un vrai Site.

**Hors périmètre :** enregistrement des Flux (0.8.0).

## Ensuite : 0.8.0 — Enregistrement continu

**Objectif.** Enregistrer sur disque, sans réencodage, le Flux des Caméras choisies : MediaMTX enregistre en segments, l’API le pilote, un interrupteur par Caméra dans l’Administration l’active ; durée de conservation fixe, les plus anciens segments sont effacés. Une tranche de bout en bout, vérifiable par l’Administrateur.

**Hors périmètre :** relecture depuis l’UI et réglages avancés (0.8.1).

## Ensuite : 0.8.1 — Relecture et réglages de l’enregistrement

**Objectif.** Relire les enregistrements d’une Caméra depuis l’UI (choisir un moment, lire), et régler l’enregistrement : durée de conservation, place disque, plages horaires.

**Hors périmètre :** fil rouge 1.0.0 (à redéfinir).

## Ensuite : 1.0.0 — Fil rouge Site → Live RTSP

**Objectif.** À redéfinir : la vidéo arrive déjà en 0.3.0. Relier bout en bout login, caméras du Site et Live sur les flux RTSP (simulés) pour qu’un utilisateur voie réellement la vidéo et puisse enchaîner les caméras — seulement si ce fil rouge a encore un job distinct une fois 0.8.x livré.

**Hors périmètre :** IA, PTZ, VPN, chiffrement des identifiants (Plus tard).

## Plus tard (pas encore numéroté)

### Réencodage H.265 → H.264 à la demande

Pour un navigateur qui ne décode pas le HEVC malgré la 0.5.0, réencoder vers H.264 seulement pendant qu’il regarde : chemin MediaMTX `camera-<id>-h264` lancé à la demande (ffmpeg), Caméra par Caméra, arrêté quand plus personne ne le lit. Le CPU du serveur n’est consommé que pendant la lecture.

### Postes de surveillance

Des écrans dédiés au Live (mini-PC, navigateur en mode kiosque, démarrage automatique sur l’UI), installés et mis à jour simplement. Le poste doit décoder le HEVC (matériel), ce qui se prête mal à un conteneur : à étudier.

### Configuration initiale du Site

Régler depuis l’Administration, au premier lancement, ce qui vit aujourd’hui dans `.env` : sous-réseaux et ports de la Détection des Caméras, origines autorisées de l’UI, etc.

### Chiffrement des identifiants RTSP

Ne plus stocker en clair le mot de passe des Caméras dans la base.

### Accès distant par VPN

Accéder au Site depuis internet par un VPN (WireGuard, Tailscale…), sans redirection de port ni UPnP.

### Détection de Flux figé ou rejoué

Repérer une Caméra `online` dont l’image est figée ou une boucle injectée (heure incrustée qui n’avance pas, images identiques, événements ONVIF de sabotage).

### Détection IA

Personnes / véhicules sur substream, après le cœur live.

### Un Appareil, plusieurs Caméras

Prendre en charge les Appareils qui portent plusieurs Caméras sous une seule adresse MAC (enregistreurs, encodeurs multi-voies, caméras à plusieurs objectifs). Il faut d’abord étudier sur du vrai matériel comment chaque voie expose son chemin RTSP, puis proposer à l’ajout toutes les voies d’un Appareil, et regrouper ses Caméras dans l’Administration. Depuis la 0.4.2, ce cas est seulement toléré : même MAC sur plusieurs Caméras, mises à jour ensemble quand l’IP change.

### PTZ

Après le paramétrage ONVIF (0.6.0) : pilotage PTZ des Caméras motorisées, et tracking éventuel.
