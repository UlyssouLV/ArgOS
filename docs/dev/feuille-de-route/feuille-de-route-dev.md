# Feuille de route de dev

Vers une **1.0.0** rudimentaire : connexion à un **Site**, onglets **Administration** (CRUD caméras, infos, états, réglages) et **Live** (une caméra en grand, bouton suivant), serveur installable, enregistrement. Pas d’IA dans ce périmètre.

Contraintes transverses :

- Chaque version a des **exigences écrites** dans les tickets / projet GitHub à l’ouverture de version.
- README type repos Ulysse : sections claires (**quoi**, **prérequis**, **comment lancer**, structure) — enrichi dès qu’une version devient lançable ; avant ça, pas de fausse « souche » runnable.
- Preuve 0.1.0 : flux RTSP simulés **joignables**, y compris un accès **navigateur** (ex. page HLS/WebRTC MediaMTX), plus tests auto (`ffprobe` / équivalent) via `/t`.
- Auth 1.0.0 : compte **local** suffit. États caméra minimaux : `unknown` / `online` / `offline`.
- **Pas d’installation sur de vraies caméras avant authentification des Flux et sécurisation d’ONVIF** (HTTPS livré en 0.6.1, Flux authentifiés en 0.6.2, ONVIF sécurisé en 0.6.3). Limites et dettes : [sécurité](../../securite.md).

## Déjà livré

- **0.1.0** — Flux RTSP simulés : MediaMTX et source en boucle, vérifiables en CLI et dans le navigateur, tests auto si le tuyau est cassé ([PR #5](https://github.com/UlyssouLV/ArgOS/pull/5)).
- **0.2.0** — API Site, auth et caméras : API d’un Site, auth locale, CRUD caméras, états `unknown` / `online` / `offline` ; identifiants RTSP encore en clair en base, masqués dans les réponses API ([PR #11](https://github.com/UlyssouLV/ArgOS/pull/11)).
- **0.3.0** — UI login, Admin et Live : frontend React branché sur l’API ; Live en WebRTC (WHEP) via MediaMTX en pont, chemins `camera-<id>` ([PR #17](https://github.com/UlyssouLV/ArgOS/pull/17), [ADR 0001](../../adr/0001-mediamtx-en-pont.md)).
- **0.4.0** — Détection des Caméras sur le réseau : Candidats (ports `554` / `8554`, `OPTIONS` RTSP, sans identifiants) ; script hôte pour les sous-réseaux ([PR #24](https://github.com/UlyssouLV/ArgOS/pull/24), [spec](../../specs/v0.4.0-detection-des-cameras.md), [ADR 0002](../../adr/0002-detection-depuis-le-reseau-bridge.md)).
- **0.4.1** — Ajout d’une Caméra depuis un Candidat : essai des chemins courants, aperçu, ajout par IP ; plus d’ajout par URL RTSP depuis l’Administration ([PR #34](https://github.com/UlyssouLV/ArgOS/pull/34), [spec](../../specs/v0.4.1-ajout-camera-depuis-candidat.md)).
- **0.4.2** — Identité stable par adresse MAC : MAC de l’Appareil, MAJ d’IP, filtre par MAC à la place de l’ajout manuel par MAC ([PR #44](https://github.com/UlyssouLV/ArgOS/pull/44), [spec](../../specs/v0.4.2-identite-stable-par-adresse-mac.md), [ADR 0003](../../adr/0003-macvlan-sur-la-prise-des-cameras.md)).
- **0.5.0** — Lecture des Flux H.265 sans réencodage : LL-HLS fMP4 pour le HEVC, WebRTC inchangé pour le H.264 ([PR #51](https://github.com/UlyssouLV/ArgOS/pull/51), [spec](../../specs/v0.5.0-lecture-flux-h265.md), [ADR 0004](../../adr/0004-hls-pour-les-flux-h265.md)).
- **0.6.0** — Paramétrage des Caméras par ONVIF : Réglages d’une Caméra active dans l’Administration, lus par ONVIF (port trouvé seul, identifiants du Flux) ; Incrustations (texte, coin, affichage du nom et de la date et heure) et Horloge (fuseau, mise à l’heure manuelle du Site, NTP en lecture seule), relues après envoi avec un statut par champ ; Caméras simulées 2 et 4 en ONVIF ; ONVIF en HTTP jusqu’à la 0.6.3 ([PR #58](https://github.com/UlyssouLV/ArgOS/pull/58), [spec](../../specs/v0.6.0-parametrage-des-cameras-par-onvif.md), [doc](../../cameras/parametrer-une-camera.md)).
- **0.6.1** — HTTPS : UI, API et Live sous une seule origine HTTPS (nginx de `web`, port `443`), `80` / `8080` redirigent, ports `8000` / `8888` / `8889` fermés, cookie de session `Secure`, fin de CORS ; certificat signé par l’Autorité du Site générée au premier lancement, régénéré seul (IP, expiration), ou certificat fourni par l’Administrateur ; lanceur Mac en HTTPS et Autorité proposée au trousseau ([PR #67](https://github.com/UlyssouLV/ArgOS/pull/67), [spec](../../specs/v0.6.1-https.md), [ADR 0005](../../adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md), [doc](../../features/reseau/installer-l-autorite-du-site.md)).
- **0.6.2** — Authentification des Flux : WHEP et HLS relayés par nginx seulement à une session ArgOS (`auth_request`, `401` sinon), l’UI revient à la connexion quand un Flux est refusé ; RTSP `8554` n’est plus publié sur l’hôte (dev : `127.0.0.1` seulement) ; MediaMTX reste sans authentification derrière le réseau Compose ; un Live WebRTC déjà établi continue après la fin de la session (Plus tard) ([PR #74](https://github.com/UlyssouLV/ArgOS/pull/74), [spec](../../specs/v0.6.2-authentification-des-flux.md), [ADR 0006](../../adr/0006-flux-authentifies-par-nginx.md)).
- **0.6.3** — Sécurisation d’ONVIF : ONVIF en HTTPS sur `443` quand la caméra le propose, clé du Certificat de l’Appareil mémorisée au premier contact puis vérifiée (clé changée ou HTTPS disparu refusés et signalés, l’Administrateur fait confiance au nouveau certificat ou l’oublie) ; ONVIF en clair seulement sur accord de l’Administrateur, mémorisé et révocable ; TLS ancien accepté et signalé ; mot de passe de caméra court (< 12 caractères) signalé à l’ajout ; port, clé et accord gardés tant que l’hôte ne change pas ; `# NOSONAR` de la 0.6.0 justifiés pour de bon. Bug connu : modifier l’URL d’une Caméra sans retaper son mot de passe enregistre `***` ([#86](https://github.com/UlyssouLV/ArgOS/issues/86), Plus tard) ([PR #85](https://github.com/UlyssouLV/ArgOS/pull/85), [spec](../../specs/v0.6.3-securisation-d-onvif.md), [ADR 0007](../../adr/0007-onvif-en-https-par-cle-memorisee.md), [doc](../../cameras/parametrer-une-camera.md)).
- **0.6.4** — Réglages image et vidéo par ONVIF : sections Image (filtre infrarouge jour / nuit / automatique, luminosité, contraste, saturation, netteté, contre-jour, WDR ; de l’Appareil, partagée par ses Caméras) et Encodage du Flux (résolution, images par seconde, débit max ; codec, qualité et intervalle entre images clés en lecture seule) dans les Réglages, relues après envoi avec un statut par champ ; profil retenu d’après l’URL RTSP de la Caméra ; Encodage par le média 2, par le média 1 seulement en H.264, sinon non réglable ; confirmation avant la coupure du Flux ; lecteur du Flux dans le panneau ; Caméra simulée 2 avec service image et média 2. Bug connu : la suite de tests échoue quand des Caméras de dev sont déclarées sur les Caméras simulées ([#95](https://github.com/UlyssouLV/ArgOS/issues/95), Plus tard) ([PR #94](https://github.com/UlyssouLV/ArgOS/pull/94), [spec](../../specs/v0.6.4-reglages-image-et-video-par-onvif.md), [ADR 0008](../../adr/0008-encodage-par-media-2-media-1-seulement-en-h264.md), [doc](../../cameras/parametrer-une-camera.md)).
- **0.7.0** — Site installable sans le dépôt : images `ghcr.io/ulyssoulv/argos-<service>:<ARGOS_VERSION>`, compose de prod autonome, install Ubuntu dans `/opt/argos` avec systemd ; Mac toujours depuis le clone (lanceur, Caméras simulées) ([PR #101](https://github.com/UlyssouLV/ArgOS/pull/101), [spec](../../specs/v0.7.0-site-installable-sans-le-depot.md), [ADR 0009](../../adr/0009-images-du-depot-et-compose-autonome.md)).
- **0.7.1** — Intégration continue : chaque PR vers `main` lance la suite (`/t -a`, stack Docker) via GitHub Actions ; check **`ArgOS tests`** à exiger pour protéger `main` ([PR #106](https://github.com/UlyssouLV/ArgOS/pull/106), [spec](../../specs/v0.7.1-integration-continue.md)).
- **0.7.2** — Livraison continue : images ghcr multi-arch (`:staging` après CI verte sur `main`, promotion digests aux Releases `vX.Y.Z`), install / MAJ Ubuntu par pull + artefact de Release, doc VLAN et staging machines perso ([PR #113](https://github.com/UlyssouLV/ArgOS/pull/113), [spec](../../specs/v0.7.2-livraison-continue.md), [ADR 0010](../../adr/0010-canaux-staging-et-production-par-retag.md)).
- **0.8.0** — Enregistrement continu : segments fMP4 (~1 min, rétention 1 h) via MediaMTX, volume Docker nommé, interrupteur et indicateur dans l’Administration ([PR #120](https://github.com/UlyssouLV/ArgOS/pull/120), [spec](../../specs/v0.8.0-enregistrement-continu.md), [ADR 0011](../../adr/0011-enregistrement-continu-par-mediamtx.md)).

## Prochaine : 0.8.1 — Suivi du stockage et du débit d’écriture

**Objectif.** Une page **Enregistrement** montre l’espace disque disponible, le débit d’écriture par Caméra si possible et le débit global selon les Caméras configurées / actives, pour estimer jusqu’où tient la conservation (et donc à quelle cadence purger). L’Administrateur règle aussi la durée de conservation et un seuil de place disque à partir de ces indications.

**Hors périmètre :** relecture des enregistrements (0.8.2), plages horaires d’enregistrement.

## Ensuite : 0.8.2 — Relecture des enregistrements

**Objectif.** Parcourir et relire les enregistrements de chaque Caméra depuis l’UI : choisir un moment, lire.

**Hors périmètre :** plages horaires d’enregistrement, fil rouge 1.0.0 (à redéfinir).

## Ensuite : 0.9.0 — Le Site, serveur de temps des Caméras

**Objectif.** Le Site sert l’heure (NTP) sur le réseau des caméras, et chaque Caméra est réglée pour s’y caler : une heure juste et commune à toutes, sans accès à internet ni remise à l’heure manuelle. Remplace le bouton « Mettre à l’heure du Site » de la 0.6.0.

**Hors périmètre :** fil rouge 1.0.0.

## Ensuite : 1.0.0 — Fil rouge Site → Live RTSP

**Objectif.** À redéfinir : la vidéo arrive déjà en 0.3.0. Relier bout en bout login, caméras du Site et Live sur les flux RTSP (simulés) pour qu’un utilisateur voie réellement la vidéo et puisse enchaîner les caméras — seulement si ce fil rouge a encore un job distinct une fois 0.8.x / 0.9.0 livrés.

**Hors périmètre :** IA, PTZ, VPN, chiffrement des identifiants (Plus tard).

## Plus tard (pas encore numéroté)

### Réencodage H.265 → H.264 à la demande

Pour un navigateur qui ne décode pas le HEVC malgré la 0.5.0, réencoder vers H.264 seulement pendant qu’il regarde : chemin MediaMTX `camera-<id>-h264` lancé à la demande (ffmpeg), Caméra par Caméra, arrêté quand plus personne ne le lit. Le CPU du serveur n’est consommé que pendant la lecture.

### Postes de surveillance

Des écrans dédiés au Live (mini-PC, navigateur en mode kiosque, démarrage automatique sur l’UI), installés et mis à jour simplement. Le poste doit décoder le HEVC (matériel), ce qui se prête mal à un conteneur : à étudier.

### Configuration initiale du Site

Régler depuis l’Administration, au premier lancement, ce qui vit aujourd’hui dans `.env` : sous-réseaux et ports de la Détection des Caméras, IP du Site, etc.

### Chiffrement des identifiants RTSP

Ne plus stocker en clair le mot de passe des Caméras dans la base.

### Accès distant par VPN

Accéder au Site depuis internet par un VPN (WireGuard, Tailscale…), sans redirection de port ni UPnP.

### Réseau Site : DHCP caméras et isolement (une prise / VLAN)

Deux situations d’install encore mal couvertes après la 0.7.2 (doc VLAN / deux prises seulement) :

1. **Pas de routeur** sur le réseau des caméras → pas de DHCP → caméras sans IP utile → la Détection ne les trouve pas. Le Site pourrait servir le DHCP sur cette prise (ex. `dnsmasq`), ou guider clairement les IP fixes.
2. **Routeur Wi‑Fi / box voulu**, mais caméras isolées : le routeur ne doit voir que le serveur ; le serveur parle au routeur pour la MAJ / futurs services. Avec **une seule prise Ethernet**, compartimenter via **VLAN** (switch managé, trunk) plutôt qu’un seul L2 partagé (conflit de DHCP, perte d’isolement). Alternative matérielle : seconde NIC (USB-Ethernet).

Objectif produit : poser / documenter (et éventuellement automatiser) ces topologies pour qu’un Administrateur non spécialiste isole les caméras sans se battre avec le réseau.

### Détection de Flux figé ou rejoué

Repérer une Caméra `online` dont l’image est figée ou une boucle injectée (heure incrustée qui n’avance pas, images identiques, événements ONVIF de sabotage).

### Détection IA

Personnes / véhicules sur substream, après le cœur live.

### Un Appareil, plusieurs Caméras

Prendre en charge les Appareils qui portent plusieurs Caméras sous une seule adresse MAC (enregistreurs, encodeurs multi-voies, caméras à plusieurs objectifs). Il faut d’abord étudier sur du vrai matériel comment chaque voie expose son chemin RTSP, puis proposer à l’ajout toutes les voies d’un Appareil, et regrouper ses Caméras dans l’Administration. Depuis la 0.4.2, ce cas est seulement toléré : même MAC sur plusieurs Caméras, mises à jour ensemble quand l’IP change.

### PTZ

Après le paramétrage ONVIF (0.6.0) : pilotage PTZ des Caméras motorisées, et tracking éventuel.

### Catalogue du matériel connu

Retenir par modèle de caméra ce qu’on sait (port ONVIF, chemins RTSP, réglages qui marchent ou non) pour accélérer l’ajout et les Réglages.

### Recherche des caméras ONVIF sur le réseau (WS-Discovery)

Trouver les caméras par l’annonce ONVIF plutôt qu’en essayant les ports courants.

### Identifiants ONVIF distincts

Permettre des identifiants ONVIF autres que ceux du Flux, pour les marques qui séparent les comptes (Hikvision…).

### Couper un Live WebRTC à la fin de la session

Depuis la 0.6.2, la session n’est vérifiée qu’à l’ouverture d’un Flux : un Live WebRTC déjà établi continue après la déconnexion ou l’expiration de la session (`docs/securite.md`). Fermer aussi ces Lives quand la session se termine.

### Bug — Modifier l'URL d'une Caméra sans retaper son mot de passe enregistre *** comme mot de passe (#86)

**Constat :** Dans **Modifier**, le champ « URL RTSP » d'une Caméra protégée par mot de passe s'affiche masqué (`rtsp://admin:***@…`). Si l'on change autre chose dans ce champ (chemin, requête, port) sans retaper le mot de passe, ArgOS enregistre `***` comme mot de passe : la Caméra passe `offline` et ses Réglages affichent « La caméra refuse ces identifiants en ONVIF. ».

**Reproductibilité :** Caméra simulée 2 déclarée avec `admin:argos-simulee` ; **Modifier** → changer seulement `subtype=0` en `subtype=1` dans l'URL masquée → **Enregistrer** : la Caméra passe `offline`, l'URL stockée porte `***`. Enregistrer l'URL masquée inchangée garde bien le mot de passe.

**Impact :** L'Administrateur qui corrige le chemin ou le port d'une Caméra perd son mot de passe sans avertissement : plus de Live, plus de Réglages, jusqu'à ce qu'il retape l'URL entière. Depuis la 0.6.3, une Caméra en ONVIF en clair afficherait en plus « Mot de passe court ». Le contact ONVIF (clé, port, accord) reste gardé.

**Cause probable :** `modifier()` (`api/argos_api/cameras.py:368`) ne reconnaît que l'URL masquée renvoyée à l'identique ; toute autre URL est stockée telle quelle, `***` compris.

**À corriger :** Modifier le chemin, la requête ou le port d'une Caméra sans retaper son mot de passe le garde ; seul un mot de passe réellement saisi le remplace.

**Hors périmètre :** Aucun.

**Suivi :** [#86](https://github.com/UlyssouLV/ArgOS/issues/86) (`bug`). Trouvé dans : 0.6.3 · Contexte : test humain · Date : 2026-10-16 · Priorité : Informations manquantes.

### Bug — La suite de tests échoue quand des Caméras de dev sont déclarées sur les Caméras simulées (#95)

**Constat :** Avec des Caméras de dev déclarées sur les Caméras simulées 2 et 4 (« Caméra simulée 2 » et « Caméra simulée 4 », gardées pour le debugging), la suite complète échoue hors du code testé : 10 tests de `tests/api/` (`test_essai.py`, `test_suivi_adresse.py`) et 15 de `tests/web/` (`test_filtre_mac.py`…). L'essai répond `409` « déjà configurée » au lieu de `200`.

**Reproductibilité :** Déclarer dans l'Administration une Caméra sur `camera-simulee-4` (ou `172.30.0.12` pour la 2), puis lancer `/t -a` : `test_essai.py` échoue sur `assert reponse.status_code == 200` (`409`), comme `test_suivi_adresse.py` et `test_filtre_mac.py`. Les retirer rend la suite verte.

**Impact :** La suite des tests ne peut pas être verte tant que le développeur garde des Caméras de dev sur les Caméras simulées : il faut choisir entre ses Caméras de debugging et une suite verte, et les vrais échecs se noient dans ces faux.

**Cause probable :** La stack des tests est la stack de dev (même base). L'essai et le rapprochement par adresse et MAC comptent toute Caméra déclarée sur l'adresse d'une Caméra simulée, désactivée comprise ; ces tests supposent que les simulées 2 et 4 ne sont pas encore déclarées.

**À corriger :** La suite des tests passe quelles que soient les Caméras que le développeur a déclarées dans sa stack de dev, sans qu'il ait à les retirer.

**Hors périmètre :** Aucun.

**Suivi :** [#95](https://github.com/UlyssouLV/ArgOS/issues/95) (`bug`). Trouvé dans : 0.6.4 · Contexte : suite de tests (implémentation de #89) · Date : 2026-10-16 · Priorité : Informations manquantes.
