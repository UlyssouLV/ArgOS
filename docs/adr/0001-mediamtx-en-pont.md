# MediaMTX en pont entre les Caméras et le navigateur

Un navigateur ne lit pas le RTSP : il faut un relais qui remballe le Flux en WebRTC. Nous faisons de MediaMTX ce relais pour **toute** Caméra du Site : l'API réconcilie en continu les Caméras actives avec des chemins MediaMTX `camera-<id>` (source = URL RTSP de la Caméra, tirée seulement quand quelqu'un regarde), via l'API de contrôle de MediaMTX, non publiée hors du réseau Compose.

## Considered Options

- **Servir seulement les chemins des Caméras simulées** (`cam1`–`cam3`) : plus simple pour la 0.3.0, mais tout serait à refaire à la première vraie caméra.
- **Synchroniser MediaMTX à chaque opération du CRUD** plutôt que réconcilier : plus immédiat, mais un MediaMTX indisponible ferait échouer ou diverger le CRUD. La réconciliation (au démarrage puis toutes les 10 s) rattrape seule tout écart.

## Consequences

- L'API dépend de l'API de contrôle MediaMTX ; MediaMTX devient la seule porte vidéo vers le navigateur (WebRTC uniquement, sans réencodage).
- La sonde d'état continue de sonder la Caméra directement, pas le relais.
- Les chemins `camera-<id>` sont lisibles sans authentification sur le réseau local tant que l'authentification des Flux n'existe pas (voir `docs/securite.md`).
