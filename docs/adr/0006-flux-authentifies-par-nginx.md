# Flux authentifiés par nginx, MediaMTX sans authentification derrière le réseau Compose

Complète l'[ADR 0005](0005-https-par-une-origine-unique-et-une-autorite-du-site.md) (une seule origine HTTPS) et l'[ADR 0001](0001-mediamtx-en-pont.md) (MediaMTX en pont). Depuis la 0.6.2, regarder une Caméra passe par la connexion d'ArgOS : **nginx** (`web`) vérifie la session ArgOS auprès de l'API (`auth_request`, cookie de session) à **chaque** requête `/flux/webrtc/…` (WHEP) et `/flux/hls/…` (HLS), et ne relaie vers MediaMTX qu'après une réponse `2xx`. RTSP `8554` n'est plus publié sur l'hôte. **MediaMTX garde `user: any`** dans `media/mediamtx.yml` : ce n'est pas un oubli, sa frontière est le réseau Compose, que seuls `web` et `api` utilisent pour le joindre.

## Considered Options

- **Authentification HTTP externe de MediaMTX** (`authMethod: http`, MediaMTX appelle l'API à chaque lecture) : couvrirait aussi RTSP, mais le cookie `HttpOnly` du navigateur ne lui parvient pas simplement ; il faudrait un jeton dans l'URL des Flux, visible dans les journaux et l'historique.
- **JWT vérifiés par MediaMTX** (`authMethod: jwt`) : sans appel à l'API par requête, mais l'API devrait émettre et faire circuler des jetons, et une déconnexion ne les révoque pas avant leur expiration.
- **RTSP publié avec un identifiant MediaMTX** : garde un accès VLC / NVR depuis le réseau local, mais ajoute un mot de passe partagé à gérer, en clair sur le réseau (pas de RTSPS), sans consommateur légitime hors de l'hôte.
- **Identifiant de lecture interne** (nginx l'ajoute après `auth_request`) : défense en profondeur contre un conteneur compromis du réseau Compose, mais presque nulle tant que l'API de contrôle `9997`, ouverte sur ce réseau, lit déjà les URL des Caméras avec leurs mots de passe.

## Consequences

- Une seule source de vérité sur la session (l'API), au même endroit que l'origine HTTPS ; aucun jeton dans les URL des Flux. Coût : une sous-requête à l'API par requête HLS (playlists, segments).
- Le contrôle porte sur l'**ouverture** d'un Flux : un Live WebRTC déjà établi continue après déconnexion ou expiration (média en UDP `8189`, hors de nginx) ; un Live HLS s'arrête à la requête suivante.
- Toute session valide lit tout chemin du pont ; des droits par Caméra demanderont autre chose que ce contrôle tout-ou-rien.
- Republier `8554` (ou exposer `8888` / `8889`) rouvre un accès libre aux Flux : à proscrire (`docs/securite.md`).
- Un conteneur compromis du réseau Compose lit les Flux sans session ; le traiter va de pair avec l'authentification de l'API de contrôle.
