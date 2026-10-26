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
| [0008](./0008-encodage-par-media-2-media-1-seulement-en-h264.md) | Encodage réglé par le média 2, média 1 seulement en H.264 |
| [0009](./0009-images-du-depot-et-compose-autonome.md) | Images du dépôt et compose autonome, une seule branche |
| [0010](./0010-canaux-staging-et-production-par-retag.md) | Canaux staging et production par retag de digest |
| [0011](./0011-enregistrement-continu-par-mediamtx.md) | Enregistrement continu par MediaMTX |
| [0012](./0012-suivi-stockage-et-conservation-reglable.md) | Suivi stockage et conservation réglable sur le volume actuel |
| [0013](./0013-relecture-des-enregistrements.md) | Relecture des enregistrements (transport et granularité) |
| [0014](./0014-serveur-de-temps-du-site.md) | Serveur de temps du Site sur le réseau des caméras |
| [0015](./0015-mise-a-l-heure-a-chaque-verification.md) | Mise à l’heure des Caméras à chaque vérification |
| [0016](./0016-tailwind-et-shadcn-ui-pour-l-ui-du-site.md) | Tailwind et shadcn/ui pour l’UI du Site |
| [0017](./0017-conservation-en-jours-et-relecture-a-la-journee.md) | Conservation en jours et Relecture à la journée |
