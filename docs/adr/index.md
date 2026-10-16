# Architecture Decision Records (ADR)

Un **ADR** fixe une décision technique : ce qu’on a choisi, pourquoi, et ce que ça implique ensuite.

Ce n’est ni une spec produit, ni un tutoriel. C’est le journal des choix structurants. Une ADR déjà écrite ne se réécrit pas : si la décision change, on en ajoute une nouvelle.

## Décisions

| N° | Décision |
| --- | --- |
| [0001](./0001-mediamtx-en-pont.md) | MediaMTX en pont entre les Caméras et le navigateur |
| [0002](./0002-detection-depuis-le-reseau-bridge.md) | Détection depuis le réseau bridge |
| [0003](./0003-macvlan-sur-la-prise-des-cameras.md) | macvlan sur la prise des caméras |
| [0004](./0004-hls-pour-les-flux-h265.md) | HLS pour les Flux H.265 |
| [0005](./0005-https-par-une-origine-unique-et-une-autorite-du-site.md) | HTTPS, origine unique et Autorité du Site |
| [0006](./0006-flux-authentifies-par-nginx.md) | Flux authentifiés par nginx, MediaMTX derrière le réseau Compose |
| [0007](./0007-onvif-en-https-par-cle-memorisee.md) | ONVIF en HTTPS par clé mémorisée, repli HTTP consenti |
