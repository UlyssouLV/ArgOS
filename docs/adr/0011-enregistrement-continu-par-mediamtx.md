# Enregistrement continu par MediaMTX

Le Live tire déjà le RTSP à la demande (`sourceOnDemand`, ADR 0001). L’enregistrement continu exige l’inverse pour les Caméras choisies : MediaMTX écrit des segments **fMP4** sans réencodage sur un **volume Docker nommé**, l’API active `record` et coupe le mode à la demande **seulement** quand l’enregistrement est ON. Conservation courte fixe (1 h en 0.8.0) via `recordDeleteAfter` ; pas de relecture HTTP dans cette décision.

## Considered Options

- **Enregistreur externe (ffmpeg côté API)** : contrôle fin, mais second pipeline, réencodage ou copie à gérer, hors du pont déjà en place.
- **Toujours tirer le RTSP pour toute Caméra active** : simple, mais charge inutile sur les Caméras non enregistrées et le réseau.
- **Bind mount / disque dédié dès l’install** : utile pour la prod longue durée ; reporté avec le suivi stockage (0.8.1).

## Consequences

- ADR 0001 reste vrai pour le Live et les Caméras sans enregistrement ; l’enregistrement ON est l’exception qui force le tirage continu.
- Un volume `enregistrements` (nom Compose) grossit comme la DB : pas de quota à l’install.
- L’API monte ce volume en lecture seule pour l’indicateur Admin et efface `camera-<id>/` à la suppression d’une Caméra.
- Pas d’exposition HTTP des segments tant que la relecture (0.8.2) n’existe pas.
