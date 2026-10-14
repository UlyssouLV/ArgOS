# Sécurité : limites connues et choix

> Notes à relire avant toute installation sur de vraies caméras, et avant chaque version qui touche au réseau, à l'authentification ou aux Flux. Rédigé à l'ouverture de la 0.2.0.

Installation type visée : un **serveur hôte sur site**, des **Caméras** réparties sur la propriété, tout relié au **même réseau local**. Ce réseau peut être relié au **Wi-Fi** du site, et un jour donner accès à certains éléments **depuis internet**.

## 1. Ce que prouve l'état d'une Caméra

Le Site sonde chaque Caméra active à intervalle régulier : il ouvre une session RTSP et attend **au moins un paquet vidéo**. Reçu → `online`, sinon → `offline`.

`online` prouve que **quelque chose diffuse de la vidéo à cette URL**. Ça ne prouve **pas** que c'est la vraie caméra, ni que l'image est vivante.

- **Sonde vs Flux continu** : tant que rien (enregistrement, Live) ne lit les Flux en permanence, l'état est un instantané pris toutes les N secondes, pas une surveillance continue.
- **`DESCRIBE` ne suffit pas** : une caméra au capteur ou à l'encodeur planté peut encore répondre à la description RTSP. C'est pourquoi la sonde exige un paquet vidéo.
- **Faux `offline`** : un paquet perdu sur le Wi-Fi, ou une caméra qui refuse un client de plus (beaucoup limitent à 2 à 4 connexions RTSP simultanées), donnent un `offline` ponctuel. Pas d'hystérésis pour l'instant : à ajouter si de vraies caméras en montrent le besoin.

### Rejeu / injection de Flux (« comme dans les films »)

Un attaquant présent sur le réseau se fait passer pour la caméra (même IP) et diffuse une boucle enregistrée, ou s'intercale entre la caméra et le serveur. Pour ArgOS, le Flux arrive : la Caméra est `online` et l'image semble normale.

Défenses, toutes hors de la 0.2.0 :

- **Isoler les caméras** sur un réseau à part (VLAN), sans accès internet, que seul le serveur peut joindre.
- **Authentification RTSP** obligatoire, idéalement **RTSPS** (RTSP chiffré) quand la caméra le permet.
- **Détecter une image figée ou en boucle** : heure incrustée par la caméra qui n'avance pas, images identiques à N minutes d'écart.
- **Événements ONVIF de sabotage** (« tamper ») émis par certaines caméras.

## 2. Exposition réseau

Règle : **n'exposer sur le réseau que ce qui doit l'être**, et rien sans authentification avant d'avoir de vraies caméras.

### PostgreSQL : jamais exposé

La base n'a aucun port publié : seul le conteneur `api` la joint, par le réseau interne de Docker Compose. Pour l'inspecter : `docker compose exec db psql`.

Si on publiait le port (`ports: "5432:5432"`), PostgreSQL écouterait sur **toutes** les interfaces du serveur :

1. **Tout appareil du réseau local** pourrait tenter de s'y connecter : caméras, téléphones et ordinateurs du Wi-Fi, invités, objets connectés. Seul un mot de passe protégerait l'accès, cible facile pour la force brute.
2. **Les caméras sont le maillon faible classique** : firmwares rarement mis à jour, mots de passe par défaut, portes dérobées. Une caméra compromise est une machine de l'attaquant **à l'intérieur** du réseau.
3. **La base contient des secrets** : URL RTSP **avec mots de passe en clair** (voir § 3) et sessions en cours. La lire donne l'accès à toutes les caméras ; voler une session donne l'accès à ArgOS sans mot de passe.
4. **Docker contourne le pare-feu de l'hôte** : sous Linux, un port publié par Docker passe avant les règles `ufw`. On croit avoir fermé, c'est ouvert.
5. **Le jour où le réseau touche internet** (redirection de port, **UPnP** activé par défaut sur beaucoup de box), un PostgreSQL ouvert est trouvé en quelques heures : le port 5432 est scanné en permanence.

### MediaMTX : Flux derrière la session ArgOS

Jusqu'à la 0.6.1, MediaMTX servait les Flux (RTSP, HLS, WebRTC) **sans authentification** sur tout le réseau local. Acceptable avec des Caméras simulées. Avec de vraies caméras, n'importe qui sur le Wi-Fi aurait pu regarder sans passer par la connexion d'ArgOS : le login de l'API serait devenu décoratif.

Depuis la 0.3.0, MediaMTX est le **pont** entre toute Caméra active et le navigateur ([ADR 0001](adr/0001-mediamtx-en-pont.md)) : l'API le configure pour relayer chaque Caméra active sur un chemin `camera-<id>`. Ces chemins sont lisibles **sans authentification par tout poste du réseau local** : la dette « Flux sans auth » couvre désormais **toutes** les Caméras du Site, pas seulement les simulées.

Depuis la 0.5.0, le Live et l'Aperçu lisent les Flux H.265 en **HLS** plutôt qu'en WebRTC ([ADR 0004](adr/0004-hls-pour-les-flux-h265.md)). Les chemins HLS (`camera-<id>`, `apercu-*` pendant un ajout) sont, **comme WHEP**, lisibles sans authentification par tout poste du réseau local, et pour **toute** Caméra active, quel que soit son codec : MediaMTX sert chaque chemin sur tous ses lecteurs. Un chemin n'est retiré qu'au tour de réconciliation suivant (≤ 10 s) après la désactivation ou la suppression de la Caméra.

Depuis la 0.6.1, WHEP et HLS ne sont plus publiés sur leurs ports (`8889`, `8888`) : ils passent par l'origine HTTPS du Site (`/flux/webrtc/…`, `/flux/hls/…`, § « Une origine HTTPS »). Le Flux ne circule donc plus en clair vers le navigateur, mais en 0.6.1 nginx ne demandait **aucune session** pour `/flux/` : qui connaissait le nom d'un chemin le lisait. Et **RTSP `8554` restait publié, en clair et sans authentification** : tout poste du réseau local y lisait chaque Caméra active, et l'`apercu-<jeton>` d'un ajout s'il connaissait le jeton.

Depuis la 0.6.2, **`/flux/` est derrière la session ArgOS** ([ADR 0006](adr/0006-flux-authentifies-par-nginx.md)) : à **chaque** requête `/flux/webrtc/…` (WHEP) et `/flux/hls/…` (playlists et segments LL-HLS), nginx demande d'abord à l'API (`GET /api/session`, avec le cookie du navigateur) si la session est valide. Sinon : `401`, et rien n'est relayé vers MediaMTX. Toute session valide lit tout chemin du pont (`camera-<id>`, `apercu-<jeton>`) : pas de droits par Caméra.

- **Le contrôle porte sur l'ouverture d'un Flux** (limite assumée) : un Live **WebRTC** déjà établi continue après la déconnexion ou l'expiration de la session, car la vidéo passe ensuite par `8189/udp` (DTLS-SRTP), hors de nginx. Un Live **HLS** s'arrête à la requête suivante (playlist ou segment, chaque seconde ou presque).
- **L'UI revient à la connexion** sur un Flux refusé, comme sur un `401` de l'API : négociation ou fermeture WHEP, playlist ou segment lu par hls.js, au Live comme à l'Aperçu. Le HLS natif (Safari sur iPhone) ne donne pas le code HTTP au lecteur : il affiche « Flux indisponible », et l'UI revient à la connexion au prochain appel de l'API (liste du Live relue toutes les 10 s, renouvellement de l'Aperçu).
- **RTSP `8554` n'est plus publié sur l'hôte** : seuls les conteneurs du réseau Compose y lisent les Flux. Un poste du réseau local qui ouvre `rtsp://<IP du Site>:8554/…` n'obtient rien. **Ne jamais le republier** (ni `8888`, ni `8889`) : ce serait rouvrir un accès libre, en clair, à toutes les Caméras actives, à côté de la session. Seule exception, en dev : la simulation (`compose.simulation.yaml`) le republie sur `127.0.0.1:8554`, joignable depuis la machine du développeur seulement (ffprobe, VLC).
- **MediaMTX reste sans authentification propre** (`user: any` dans `media/mediamtx.yml`) : RTSP (`8554`), WHEP (`8889`) et HLS (`8888`) ne sont joignables, sans port publié, que par les conteneurs du réseau Compose, et nginx ne relaie WHEP et HLS qu'après la vérification. Un conteneur compromis de ce réseau lit donc tous les Flux, comme il joint déjà l'API de contrôle (`9997`, ci-dessous). Un identifiant de lecture interne n'y changerait rien tant que l'API de contrôle reste ouverte en interne (ADR 0006).

Le pont n'accepte aucune publication : il ne fait que tirer les Flux des Caméras. Les Caméras simulées (dev seulement, `compose.simulation.yaml`) sont des conteneurs à part, non publiés sur la machine hôte, où seul leur ffmpeg interne publie ; `camera-simulee-2` exige un identifiant et un mot de passe de dev, publics dans le dépôt.

### MediaMTX : API de contrôle non publiée

L'API de contrôle de MediaMTX (port 9997) permet d'ajouter, modifier ou retirer des chemins, donc de relayer n'importe quelle URL RTSP. Elle est **activée sans authentification mais non publiée** dans `compose.yaml` : seuls les conteneurs du réseau Compose (dont `api`) la joignent. **Ne jamais publier ce port.** Elle lit aussi les URL des Caméras **avec leurs mots de passe en clair** (source des chemins `camera-<id>`).

### API : derrière l'origine HTTPS

Depuis la 0.6.1, l'API n'a plus de port publié : elle n'est joignable que par `web`, sous l'origine HTTPS du Site (`/api/…`), et par son healthcheck. Le mot de passe de l'Administrateur, le cookie de session et les identifiants de caméra saisis à l'ajout ne circulent plus en clair sur le Wi-Fi. Le cookie porte `Secure; HttpOnly; SameSite=Lax`, à la pose comme à la suppression, sans réglage pour retirer `Secure` : le navigateur ne l'envoie jamais à une adresse `http://`.

Seules routes sans session, hors connexion : la doc de l'API (`/api/docs`) et `GET /api/instance`, qui renvoie un jeton aléatoire tiré à chaque démarrage. Ce jeton n'ouvre rien : il sert à la Détection à se reconnaître elle-même pour ne jamais se lister comme Candidat. Depuis la 0.6.2, l'hôte du Site ne répond plus en RTSP (`8554` n'est plus publié) : ce contrôle n'est plus qu'un garde-fou, au cas où `8554` (ou `554`) serait republié sur l'hôte.

### Détection : ArgOS agit sur le réseau

Depuis la 0.4.0, ArgOS n'attend plus seulement les Caméras qu'on lui donne : la **Détection** frappe à toutes les portes des sous-réseaux autorisés. Explication complète : [Réseau du Site et Détection des Caméras](cameras/reseau-et-detection.md).

- **Ce qu'elle envoie** : depuis le conteneur `api`, une connexion TCP vers chaque adresse des sous-réseaux, sur chaque port caméra (`ARGOS_DETECTION_CAMERAS_PORTS`, défaut `554,8554`) ; si elle est acceptée, une requête RTSP `OPTIONS` **sans chemin ni identifiants**. Puis, aux seuls hôtes qui ont répondu en RTSP, `GET /api/instance` sur le port HTTPS du Site (`ARGOS_PORT_HTTPS`, `443` par défaut), pour écarter ArgOS lui-même : un hôte n'est reconnu que s'il renvoie le jeton de cette instance en présentant exactement le certificat du Site. Aucun mot de passe n'est essayé, rien n'est écrit sur les appareils.
- **À qui** : uniquement aux sous-réseaux de `ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX`. Ils viennent de l'**hôte** : le script `scripts/cameras/configurer-detection.sh` les recalcule à chaque lancement depuis la ou les prises retenues pour les caméras ([ADR 0002](adr/0002-detection-depuis-le-reseau-bridge.md)), ou l'installateur les écrit à la main. Le fichier de simulation (dev) y ajoute `172.30.0.0/24`. L'API ne choisit jamais seule où chercher.
- **Plafond** : **1024 adresses** au total ; au-delà, ou réglage invalide, la Détection est indisponible (le reste d'ArgOS tourne). 128 connexions simultanées au plus, 1,5 s par essai, **une seule Détection à la fois** (une seconde reçoit `409`).
- **Réservée à l'Administrateur** : `GET` et `POST /api/detection` exigent une session (`401` sinon) : un inconnu du réseau ne peut pas faire balayer le réseau par ArgOS.
- **Visible** : ce balayage ressemble à celui d'un attaquant. Un pare-feu, un IDS ou une caméra qui journalise peuvent le signaler ; prévenir qui gère le réseau du Site. Chaque Détection écrit ses Candidats et son bilan dans `docker compose logs api`.
- **Ce qu'elle révèle** : les Candidats (IP, port, statut RTSP, en-tête `Server`, souvent marque et firmware) ne sont pas stockés, mais ils sont renvoyés à l'Administrateur et écrits dans les journaux.

### Ajout d'une Caméra : ArgOS essaie un Flux

Depuis la 0.4.1, **Ajouter** sur un Candidat (ou **Ajouter par adresse IP**) fait chercher son Flux par ArgOS : `OPTIONS`, puis `DESCRIBE` sur une liste de chemins courants, avec les identifiants saisis s'il y en a, puis la sonde (un paquet vidéo). Déroulé complet : [Ajouter une Caméra](cameras/ajouter-une-camera.md).

- **Garde-fous de l'essai** : réservé à une session (`401` sinon), pour qu'un inconnu du réseau ne s'en serve pas pour deviner des mots de passe ; **un seul essai à la fois** pour le Site (un second reçoit `409`) ; IP du **réseau local** seulement (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, sinon `422`), jamais ArgOS lui-même (`422`) ni une Caméra déjà configurée (`409`).
- **Pas de force brute par ArgOS** : un seul essai d'identifiants par demande. Au premier `401`, l'essai s'arrête, sans autre chemin, sans réessai automatique, sans mots de passe par défaut : ArgOS ne fait pas verrouiller la caméra.
- **Mot de passe sur le réseau** : depuis la 0.6.1, l'identifiant et le mot de passe de la caméra vont du navigateur à l'API (`POST /api/essai`) en HTTPS, comme le mot de passe de l'Administrateur. Vers la caméra, RTSP les envoie en Digest ou en Basic selon ce qu'elle demande : en Basic, ils sont lisibles sur le réseau des caméras.
- **En clair en base** : la Caméra ajoutée garde ses identifiants dans son URL RTSP, en clair en base, masqués (`***`) dans les réponses de l'API (§ 3). Une fois envoyé, le mot de passe ne revient jamais au navigateur : l'URL de l'essai reste côté serveur, et la Caméra est créée à partir d'elle.
- **Journaux** : une ligne par essai (IP, port, issue, chemin, codec), jamais d'identifiant ni d'URL complète.
- **Aperçu** : pendant l'ajout, le pont relaie le Flux sur `apercu-<jeton aléatoire>`. Depuis la 0.6.2, WHEP et HLS exigent la session ArgOS, comme pour les autres Flux (`401` sinon), et RTSP (`8554`) n'est plus joignable que du réseau Compose. Le jeton aléatoire n'est donné qu'à l'Administrateur : il ne se devine pas, et circule en HTTPS depuis la 0.6.1 (API, WHEP, HLS). Un seul Aperçu à la fois, retiré à l'ajout, à l'annulation, au remplacement, ou 2 minutes sans renouvellement (`ARGOS_APERCU_EXPIRATION_S`) ; les `apercu-*` orphelins sont retirés au démarrage de l'API.

### Réseau des caméras : une sortie seulement

Depuis la 0.4.2, en prod Linux, `api` rejoint le réseau des caméras par une interface **macvlan** (`compose.reseau-cameras.yaml`, [ADR 0003](adr/0003-macvlan-sur-la-prise-des-cameras.md)) pour y lire les adresses MAC. Explication complète : [Reconnaître un Appareil](cameras/reseau-et-detection.md#9-reconnaître-un-appareil--mac-arp-réseau-des-caméras).

- **Sortie seulement** : `api` y parle aux caméras (Détection, essai, sonde), mais toute requête HTTP arrivée sur son adresse de ce réseau reçoit `403` avant tout traitement (ni routage, ni session ; une connexion WebSocket est fermée). Une caméra compromise ne peut donc ni appeler l'API, ni tenter le mot de passe de l'Administrateur. Le healthcheck (`localhost`) et le bridge (UI, postes du réseau de la box) restent servis.
- **Une IP d'ArgOS sur ce réseau** : fixe (`ARGOS_RESEAU_CAMERAS_IP`), proposée par le script hôte parmi les adresses libres (vérifiées par ARP), à garder **hors de la plage DHCP**. Elle n'est jamais un Candidat. Le script avertit et désactive le réseau des caméras si elle sort du sous-réseau ou si un autre appareil y répond.
- **Ce que la sonde lit** : après chaque connexion réussie (Détection, essai, état), la table de voisinage (ARP) du conteneur, pour l'IP qui vient de répondre : seulement sa MAC. Rien n'est envoyé de plus aux caméras ; l'ARP est le mécanisme ordinaire de tout appareil du réseau local. Les MAC sont gardées en base avec les Caméras, et affichées à l'Administrateur.
- **Ce que la MAC prouve** : qu'un **autre** appareil répond à l'adresse d'une Caméra (elle passe `offline`, « autre appareil à cette adresse », et le pont cesse de la relayer). Elle ne prouve **pas** que c'est la vraie caméra : une MAC se falsifie sans peine. Elle protège d'une erreur (bail DHCP repris), pas d'un attaquant sur le réseau des caméras (§ 1, rejeu).
- **Pas de MAC** sous Docker Desktop (Mac), derrière un routeur, ni sur une autre prise que la première retenue : ces Caméras gardent le comportement de la 0.4.1.

### Une origine HTTPS

Depuis la 0.6.1, le Site n'est servi que par **une seule origine HTTPS**, `https://<IP du Site>` ([ADR 0005](adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md)) : le nginx du conteneur `web` termine le TLS sur le port `443` et relaie l'UI, l'API (`/api/`) et le Live (`/flux/webrtc/`, `/flux/hls/`) vers les conteneurs, par le réseau Compose. Schéma complet, chaque flux marqué chiffré ou en clair : [Schéma du réseau et des Flux](features/reseau/schema-flux.md).

- **Ports publiés** : `443` (HTTPS) ; `80` et `8080`, qui ne font que rediriger vers HTTPS (`301`) et servir la partie publique de l'Autorité (`/argos-ca.crt`) ; `8189/udp` (média WebRTC, chiffré en DTLS-SRTP). L'API, WHEP et HLS n'ont plus de port publié depuis la 0.6.1, RTSP `8554` depuis la 0.6.2 : pas de chemin en clair à côté de l'origine HTTPS.
- **Plus de CORS** : l'UI et l'API partagent l'origine, le front n'utilise que des URL relatives. Aucune autre page n'est autorisée à lire l'API : ses réponses ne portent pas `Access-Control-Allow-Origin`. (MediaMTX garde le sien sur `/flux/`, ouvert à toute origine ; depuis la 0.6.2, nginx n'y relaie qu'une requête qui porte une session valide, et le cookie `SameSite=Lax` n'est pas envoyé par la page d'un autre site.)
- **Ce que le HTTPS protège** : sur le Wi-Fi, le mot de passe de l'Administrateur, le cookie de session, les identifiants de caméra saisis à l'ajout, le jeton de l'Aperçu et le Live ne se lisent plus, et un poste du réseau ne peut plus se faire passer pour le Site **auprès d'un poste qui a installé l'Autorité**.
- **Ce qu'il ne protège pas** : le réseau des caméras (RTSP, ONVIF) ; un poste qui accepte un avertissement de certificat. Un avertissement du navigateur ne se contourne jamais : il signale une Autorité pas installée, une adresse que le certificat ne nomme pas, ou une usurpation.
- **Limite « same-site »** : le cookie est `SameSite=Lax`, et le « site » ne tient compte ni du port ni du schéma. Une autre application servie sur le même hôte (autre port) est same-site : le navigateur lui envoie le cookie d'ArgOS sur ses requêtes vers `https://<IP du Site>/api/…`. Elle ne peut pas lire les réponses (pas de CORS), mais peut envoyer une requête « simple » (formulaire `POST`) : ne rien héberger d'autre de non fiable sur le serveur d'ArgOS.

### Autorité du Site : qui a la clé

Le certificat du serveur est signé par l'**Autorité du Site**, créée au premier lancement par le service ponctuel `certificats` (10 ans), puis installée par l'Administrateur sur chacun de ses postes : [Installer l'Autorité du Site](features/reseau/installer-l-autorite-du-site.md). Un poste qui l'a installée fait confiance à **tout** certificat qu'elle signe, pour n'importe quel nom : sa clé est le secret le plus sensible du Site.

- **La machine hôte, c'est la confiance totale** : qui l'administre (ou a accès à Docker sur elle) lit le volume `autorite`, donc la clé, et peut signer un certificat que les postes accepteront, y compris pour un autre site que l'ArgOS. Ne donner l'accès à l'hôte qu'à qui on confierait les postes.
- **La clé n'est montée que dans `certificats`** : un conteneur ponctuel, sans port, qui ne tourne que le temps de créer ou de vérifier les certificats au démarrage. `web`, `api`, `mediamtx` et `db` ne la voient jamais.
- **`web` compromis** (seul conteneur exposé en HTTPS) : l'attaquant obtient la **clé du certificat serveur** de cette machine, valable au plus **397 jours**, pour les seuls noms du Site (`localhost`, `127.0.0.1`, son IP). Il peut se faire passer pour ce Site, pas pour un autre. Il n'y a pas de révocation : régénérer le certificat serveur ne rend pas la clé volée inutile ; seule une nouvelle Autorité, réinstallée sur tous les postes, le fait avant l'échéance.
- **`api`** reçoit le certificat serveur seul, sans clé, pour reconnaître l'hôte du Site pendant la Détection.
- **`/argos-ca.crt`** n'est que la partie publique de l'Autorité, servie en HTTP : un poste du réseau pourrait la remplacer en route. Toujours comparer son empreinte SHA-256 à celle des journaux de `certificats` (ou du lanceur) avant de l'installer.
- **Perte du volume `autorite`** (`docker compose down -v`, réinstallation de Docker) : une nouvelle Autorité est créée au lancement suivant, à réinstaller sur **tous** les postes. Ni sauvegarde ni export dans la 0.6.1.
- **Certificat fourni** (`ARGOS_CERTIFICAT_DOSSIER`) : ni Autorité du Site, ni `/argos-ca.crt` ; la sécurité dépend alors de l'autorité qui l'a signé et de la garde de sa clé, déposée sur l'hôte et copiée pour `web`. Son renouvellement est à la charge de l'Administrateur.

### Accès depuis internet

Passer par un **VPN** (WireGuard, Tailscale…) plutôt que par une redirection de port : le serveur n'est alors joignable que par des appareils authentifiés, et rien n'est exposé à internet.

## 3. Dettes connues

| Dette | Depuis | Risque | Suite prévue |
|---|---|---|---|
| Identifiants RTSP stockés **en clair** en base (masqués dans les réponses de l'API) | 0.2.0 | Lecture de la base → accès à toutes les caméras | Chiffrement des identifiants RTSP |
| MediaMTX sans authentification propre (RTSP `8554`, WHEP, HLS, API de contrôle `9997`) : plus rien de publié sur l'hôte depuis la 0.6.2, WHEP et HLS derrière la session ArgOS, mais tout conteneur du réseau Compose lit les Flux | 0.1.0 | Un conteneur compromis du réseau Compose lit toutes les Caméras | Identifiant de lecture interne, avec l'authentification de l'API de contrôle (ADR 0006) |
| Live WebRTC déjà établi gardé après déconnexion ou expiration de la session | 0.6.2 | Un poste déconnecté voit encore la Caméra ouverte jusqu'à fermer la vue | Plus tard : couper le Live à la fin de la session |
| ONVIF en HTTP vers la caméra ; mot de passe envoyé en empreinte WS-Security (SHA-1, imposé par la norme) | 0.6.0 | Sur le réseau des caméras : empreinte capturée puis mot de passe faible cassé hors ligne, requête rejouée, réglage modifié au passage (heure incrustée) | Sécurisation d'ONVIF (0.6.3) |
| Mot de passe de l'Administrateur en clair dans `.env` | 0.2.0 | Lecture du serveur → accès à ArgOS | À revoir avec les comptes multiples |
| Frein à la force brute en mémoire | 0.2.0 | Remis à zéro à chaque redémarrage de l'API | À revoir avec les comptes multiples |

Contrainte : **pas d'installation sur de vraies caméras avant l'authentification des Flux (0.6.2) et la sécurisation d'ONVIF (0.6.3)** ; HTTPS est livré depuis la 0.6.1 (voir la [feuille de route de dev](dev/feuille-de-route/feuille-de-route-dev.md)).
