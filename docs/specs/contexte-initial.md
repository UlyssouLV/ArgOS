# Contexte initial ArgOS

> **Statut :** notes et hypothèses à la date d’init du dépôt. Ce n’est pas une spécification figée : tout peut être infirmé ou précisé par les specs de version et les ADR.

## Intention

Construire une plateforme de vidéosurveillance IP **self-hosted**, d’abord pour une grande propriété privée, avec l’ambition d’un logiciel **générique** (pas un script one-shot).

Symbolique du nom : chien d’Ulysse + Argos Panoptès (vigilance multi-caméras).

## Orientation technique (hypothèses)

- Caméras IP PoE, RTSP, idéalement ONVIF ; main stream / substream
- Pas de dépendance à une marque ; adaptateurs propriétaires seulement si nécessaire
- Backend Python + FastAPI ; frontend web React (navigateur, éventuellement kiosque)
- Docker Compose à terme : backend, frontend, PostgreSQL, MediaMTX ; puis redis / workers FFmpeg / IA selon les versions
- MediaMTX pour simuler des flux RTSP avant le matériel réel
- Enregistrement sans réencodage quand possible ; IA sur substream
- Événements centralisés ; PTZ / auto-tracking plus tard
- Sécurité : auth, secrets hors git, caméras isolées (VLAN) lorsque pertinent

## MVP progressif envisagé

1. Ajouter une caméra et tester RTSP  
2. Afficher le flux  
3. Enregistrer  
4. Multi-caméras, main/substream  
5. Événements → ONVIF → IA → PTZ / tracking  

Chaque composant optionnel doit pouvoir être absent sans casser le reste.

## Matériel / réseau

Schémas PoE, switches, fibre, dimensionnement débit/stockage : utiles pour une installation réelle, hors scope code tant qu’une version ne les formalise pas. Voir notes orales / brief initial si besoin ; ne pas les traiter comme exigences logicielles bloquantes.

## Suite

La [feuille de route de dev](../dev/feuille-de-route-dev.md) tranche l’ordre des versions. Les décisions structurantes iront dans `docs/adr/`.
