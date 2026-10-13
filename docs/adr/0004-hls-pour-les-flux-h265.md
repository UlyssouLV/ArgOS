# HLS pour les Flux H.265, WebRTC pour le reste

Complète l'[ADR 0001](0001-mediamtx-en-pont.md), dont MediaMTX reste le seul pont vers le navigateur, mais plus « WebRTC uniquement ». Les navigateurs ne lisent de façon fiable que le H.264 en WebRTC ; pour montrer les Caméras H.265 (0.5.0) **sans réencodage**, le front les lit en **LL-HLS fMP4** servi par MediaMTX, qui remballe les images telles quelles : c'est la puce vidéo du poste qui décode. Le transport est choisi d'après le **codec retenu sur la Caméra** (relevé à l'essai, rafraîchi par la sonde) : `H265` → HLS ; tout autre codec, ou inconnu → WebRTC.

## Considered Options

- **Réencoder en H.264 côté serveur** : marche dans tous les navigateurs, mais consomme du CPU en continu pour chaque Caméra H.265. Gardé comme secours à la demande (0.5.1).
- **H.265 en WebRTC** (MediaMTX 1.21 le sait) : un seul transport, mais support navigateur plus étroit que HLS (Safari récent, Chrome seulement avec décodage matériel et version récente).
- **HLS pour tous les Flux** : un seul lecteur, mais les Caméras H.264 perdraient leur latence sous la demi-seconde.
- **Essayer WebRTC puis replier sur HLS** : sans état côté Site, mais lent à démarrer et fragile à distinguer d'une panne.

## Consequences

- Deux lecteurs dans le front (WHEP, hls.js) ; le Site doit tenir le codec de chaque Caméra à jour.
- Les Caméras H.265 ont 1 à 3 s de retard dans le Live.
- Un navigateur sans décodage HEVC (Firefox, machine sans décodeur matériel) affiche un message au lieu de l'image, jusqu'au réencodage à la demande.
- Les chemins HLS sont, comme WHEP, lisibles sans authentification sur le réseau local (`docs/securite.md`).
