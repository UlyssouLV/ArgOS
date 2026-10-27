# Feuille de route de dev

Jusqu’à la **0.9.x**, le Site couvre déjà connexion, Administration, Live, enregistrement / relecture et calage horaire des Caméras. La **1.0.0** a refait toute l’interface et porté la Conservation à 30 jours : c’est le socle. Ensuite : confort de relecture et export (**1.1.x**), Live plus réactif (**1.2.0**), puis détection d’activité sur la timeline (**2.0.0** / **2.0.1**) et un passage de nettoyage des bugs ouverts (**2.0.2**).

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
- **0.8.1** — Suivi du stockage et du débit d’écriture : page Enregistrement (espace volume, débits, tenue), Conservation Site 1–24 h et Seuil de place disque (signal seul) ([PR #126](https://github.com/UlyssouLV/ArgOS/pull/126), [spec](../../specs/v0.8.1-suivi-du-stockage-et-du-debit-decriture.md), [ADR 0012](../../adr/0012-suivi-stockage-et-conservation-reglable.md)).
- **0.8.2** — Relecture des enregistrements : sur la page Enregistrement, une Caméra du résumé ouvre sa timeline sur la Conservation (plages colorées, trous visibles, Segment en écriture exclu) ; un clic lit le Segment fermé depuis son début, play / pause, enchaînement, vitesses ×1…×16 ; vidéo du serveur playback MediaMTX relayée par nginx derrière la session, sans réencodage (H.265 lisible là où le Live l’est). Une Caméra à la fois, pas de seek à la seconde ni de téléchargement (Plus tard) ([PR #132](https://github.com/UlyssouLV/ArgOS/pull/132), [spec](../../specs/v0.8.2-relecture-des-enregistrements.md), [ADR 0013](../../adr/0013-relecture-des-enregistrements.md)).
- **0.9.0** — Le Site, serveur de temps des Caméras : service `temps` (chrony) qui sert le NTP sur le réseau des caméras (macvlan, ou UDP 123 publié sur l’hôte), Heure du Site (source `pool.ntp.org` ou horloge du serveur, fuseau) réglée une fois dans l’Administration, chaque Caméra ONVIF calée dessus (`SetNTP`, mode NTP, fuseau du Site) à l’ajout, au changement et toutes les heures, avec un état par Caméra ; section Horloge et « Mettre à l’heure du Site » de la 0.6.0 retirées des Réglages. Relecture vidéo seule et réponses par plages (`206`) : Safari lit les Segments H.265 d’une Caméra qui annonce de l’audio ([#141](https://github.com/UlyssouLV/ArgOS/issues/141)) ([PR #140](https://github.com/UlyssouLV/ArgOS/pull/140), [spec](../../specs/v0.9.0-le-site-serveur-de-temps-des-cameras.md), [ADR 0014](../../adr/0014-serveur-de-temps-du-site.md)).
- **0.9.1** — Mise à l’heure à chaque vérification : à l’ajout, au changement de l’Heure du Site, toutes les heures, sur « Vérifier maintenant » et à l’instant de chaque changement d’heure, le Site pousse l’heure du Serveur de temps du Site dans chaque Caméra ONVIF active puis la recale ; dérive (avant) et écart (après) mesurés contre le Serveur de temps du Site, états à l’heure / écart / sans ONVIF / échec ; fuseau envoyé au décalage du moment (sans règles d’heure d’été, `DaylightSavings=false`) depuis la base des fuseaux de l’hôte (embarquée en secours), décalage relu vérifié ; install / MAJ Ubuntu réactivent la synchro NTP de l’OS ; Caméra simulée « NTP paresseux » ; caméras qualifiées documentées ([PR #149](https://github.com/UlyssouLV/ArgOS/pull/149), [spec](../../specs/v0.9.1-mise-a-l-heure-a-chaque-verification.md), [ADR 0015](../../adr/0015-mise-a-l-heure-a-chaque-verification.md), [doc](../../features/heure/serveur-de-temps-et-calage.md)).
- **1.0.0** — Refonte graphique totale de l’interface et Conservation en jours : toute l’UI du Site redessinée sous les mêmes capacités produit — thème sombre au rouge du logo, Inter et JetBrains Mono embarquées, Tailwind v4 et shadcn/ui ; rail latéral (Live, Enregistrement, Relecture, Administration › Caméras / Heure du Site), Live en page d’accueil avec Précédente / Suivante et flèches ← / → ; Réglages de la Caméra en panneau latéral, Détection en boîte de dialogue, suppression confirmée, toasts, squelettes et états vides ; Conservation de 1 h à 30 jours saisie en jours + heures ; Relecture sur sa propre page, un jour à la fois (Timeline 00h → 24h au fuseau du Site, sélecteur de jour). Poste fixe et tablette (≥ 768 px) ; téléphone, thème clair et seek à la seconde Plus tard ([PR #162](https://github.com/UlyssouLV/ArgOS/pull/162), [spec](../../specs/v1.0.0-refonte-graphique-totale-de-l-interface-et-conservation-en-jours.md), [ADR 0016](../../adr/0016-tailwind-et-shadcn-ui-pour-l-ui-du-site.md), [ADR 0017](../../adr/0017-conservation-en-jours-et-relecture-a-la-journee.md)).
- **1.1.0** — Relecture continue : Plages enregistrées (Segments contigus) lues sans interruption visible, une fenêtre par Segment demandée au Pont depuis l’instant lu, la suite préchargée dans une seconde `<video>` qui prend le relais ; clic sur la Timeline = lecture à la seconde visée (image clé précédente, sans promesse frame-exact), y compris pendant la lecture ; trou ou clic dans un trou → début de la Plage suivante du jour, pause après la dernière ; instant lu en HH:MM:SS au fuseau du Site ; vitesses ×1…×16, session et H.265 sans réencodage inchangés ; départ à la microseconde du premier Segment (#171), fenêtre recalée sur la vidéo d’une Caméra dont l’audio est en avance (#172), Caméra simulée audio en avance de 14 s (#173). Limite connue : sur une telle Caméra, les secondes de vidéo perdues au début de chaque Segment sautent aussi en relecture ([PR #170](https://github.com/UlyssouLV/ArgOS/pull/170), [spec](../../specs/v1.1.0-relecture-continue.md), [ADR 0018](../../adr/0018-relecture-continue-fenetre-glissante.md)).

## Prochaine : 1.1.1 — Export d’une plage

Objectif. Télécharger une plage d’enregistrement choisie (début et fin), sous un fichier utilisable hors du Site, derrière la session.

Hors périmètre : relecture continue et seek (1.1.0) ; Live plus réactif (1.2.0) ; détection d’activité (2.0.0).

## Ensuite : 1.2.0 — Live plus réactif

Objectif. Voir l’image Live plus vite à l’ouverture de la page ou au changement de Caméra.

Hors périmètre : relecture et export (1.1.x) ; détection d’activité (2.0.0).

## Ensuite : 2.0.0 — Détection d’activité sur la timeline

Objectif. Repérer les moments où il y a de l’activité sur une Caméra et les afficher comme traits sur la timeline en relecture, pour aller directement aux passages intéressants. Première livraison : activité par mouvement.

Hors périmètre : distinguer Humains, Véhicules et Animaux (2.0.1) ; export d’une plage (1.1.1) ; Live plus réactif (1.2.0).

## Ensuite : 2.0.1 — Classification Humains / Véhicules / Animaux

Objectif. Sur la timeline, distinguer les passages de personnes, de véhicules et d’animaux (traits ou marques différenciés), pour filtrer ou repérer plus vite ce qui compte.

Hors périmètre : détection par mouvement seule (2.0.0) ; export d’une plage (1.1.1) ; Live plus réactif (1.2.0) ; nettoyage des bugs (2.0.2).

## Ensuite : 2.0.2 — Nettoyage des bugs

Objectif. Corriger tous les bugs listés sous **Plus tard** (entrées `### Bug —`), pour repartir sans dettes connues après la ligne 2.0.x. Les fiches restent sous Plus tard jusqu’à la livraison (visibilité docsite / liste des bugs).

Hors périmètre : nouvelles capacités produit (1.1.x, 1.2.0, 2.0.0, 2.0.1).

## Plus tard (pas encore numéroté)

### Interface mobile

La 1.0.0 vise le poste fixe et la tablette (≥ 768 px). Sur téléphone : navigation et Live adaptés au petit écran (rail en barre basse ou menu, Live plein écran, tableaux en cartes).

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

**Constat :** Dans **modifier**, le champ « URL RTSP » d'une Caméra protégée par mot de passe s'affiche masqué (`rtsp://admin:***@…`). Si l'on change autre chose dans ce champ (chemin, requête, port) sans retaper le mot de passe, ArgOS enregistre `***` comme mot de passe : la Caméra passe `offline` et ses Réglages affichent « La caméra refuse ces identifiants en ONVIF. ».

**Reproductibilité :** Caméra simulée 2 déclarée avec `admin:argos-simulee` ; **modifier** → changer seulement `subtype=0` en `subtype=1` dans l'URL masquée → **Enregistrer** : la Caméra passe `offline`, l'URL stockée porte `***`. Enregistrer l'URL masquée inchangée garde bien le mot de passe.

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
