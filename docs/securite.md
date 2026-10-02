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

### MediaMTX : Flux sans authentification

Aujourd'hui, MediaMTX sert les Flux (RTSP, HLS, WebRTC) **sans authentification** sur tout le réseau local. Acceptable avec des Caméras simulées. Avec de vraies caméras, n'importe qui sur le Wi-Fi pourrait regarder sans passer par la connexion d'ArgOS : le login de l'API deviendrait décoratif.

Depuis la 0.3.0, MediaMTX est le **pont** entre toute Caméra active et le navigateur ([ADR 0001](adr/0001-mediamtx-en-pont.md)) : l'API le configure pour relayer chaque Caméra active sur un chemin `camera-<id>`. Ces chemins sont lisibles **sans authentification par tout poste du réseau local** : la dette « Flux sans auth » couvre désormais **toutes** les Caméras du Site, pas seulement les simulées. Un chemin n'est retiré qu'au tour de réconciliation suivant (≤ 10 s) après la désactivation ou la suppression de la Caméra.

Le pont n'accepte aucune publication : il ne fait que tirer les Flux des Caméras. Les Caméras simulées (dev seulement, `compose.simulation.yaml`) sont des conteneurs à part, non publiés sur la machine hôte, où seul leur ffmpeg interne publie ; `camera-simulee-2` exige un identifiant et un mot de passe de dev, publics dans le dépôt.

### MediaMTX : API de contrôle non publiée

L'API de contrôle de MediaMTX (port 9997) permet d'ajouter, modifier ou retirer des chemins, donc de relayer n'importe quelle URL RTSP. Elle est **activée sans authentification mais non publiée** dans `compose.yaml` : seuls les conteneurs du réseau Compose (dont `api`) la joignent. **Ne jamais publier ce port.** Elle lit aussi les URL des Caméras **avec leurs mots de passe en clair** (source des chemins `camera-<id>`).

### API : HTTP simple

L'API écoute en HTTP sur le port 8000. Sur le Wi-Fi, le mot de passe de l'Administrateur et le cookie de session circulent **en clair** ; le cookie n'a pas l'attribut `Secure`. Il faut HTTPS avant tout usage réel.

### UI et API : deux origines, CORS avec credentials

L'UI (`web`, port 8080) et l'API (port 8000) sont deux **origines** différentes sur le même hôte. Le front appelle l'API avec `credentials: 'include'` : le navigateur joint le cookie de session, et l'API doit l'autoriser par CORS.

- **Origines exactes, jamais `*`** : l'API n'autorise que les origines listées dans `ARGOS_ORIGINES_AUTORISEES` (`.env`, défaut `http://localhost:8080,http://localhost:5173`). Une autre origine ne reçoit pas `Access-Control-Allow-Origin` : le navigateur ne lui laisse pas lire les réponses, et refuse les requêtes qui demandent un préflight (JSON, `PATCH`, `DELETE`).
- **Sur le réseau local**, ajouter l'adresse ouverte dans le navigateur (ex. `http://192.168.1.20:8080`), sinon l'UI ne peut pas appeler l'API.
- **Limite « same-site »** : le cookie est `SameSite=Lax`, et le « site » ne tient compte ni du port ni du schéma. **Toute autre application servie sur le même hôte** (autre port) est donc same-site : le navigateur lui envoie le cookie d'ArgOS sur ses requêtes vers l'API. CORS l'empêche de lire les réponses, mais pas d'envoyer une requête « simple » (formulaire `POST`, par exemple) : ne rien héberger d'autre de non fiable sur le serveur d'ArgOS.

### Accès depuis internet

Passer par un **VPN** (WireGuard, Tailscale…) plutôt que par une redirection de port : le serveur n'est alors joignable que par des appareils authentifiés, et rien n'est exposé à internet.

## 3. Dettes connues

| Dette | Depuis | Risque | Suite prévue |
|---|---|---|---|
| Identifiants RTSP stockés **en clair** en base (masqués dans les réponses de l'API) | 0.2.0 | Lecture de la base → accès à toutes les caméras | Chiffrement des identifiants RTSP |
| Pas de HTTPS (API, Live) | 0.2.0 | Mot de passe et session lisibles sur le Wi-Fi | HTTPS |
| Flux MediaMTX sans authentification (`camN`, et `camera-<id>` pour toute Caméra active depuis la 0.3.0) | 0.1.0 | Accès aux Flux sans passer par ArgOS | Authentification des Flux |
| Mot de passe de l'Administrateur en clair dans `.env` | 0.2.0 | Lecture du serveur → accès à ArgOS | À revoir avec les comptes multiples |
| Frein à la force brute en mémoire | 0.2.0 | Remis à zéro à chaque redémarrage de l'API | À revoir avec HTTPS / comptes multiples |

Contrainte : **pas d'installation sur de vraies caméras avant HTTPS et authentification des Flux** (voir la [feuille de route de dev](dev/feuille-de-route-dev.md)).
