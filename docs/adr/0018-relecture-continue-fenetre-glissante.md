# Relecture continue : fenêtre glissante et seek à la seconde

L’ADR 0013 livrait la Relecture Segment par Segment (`src` = un Segment, `onEnded` → suivant) et un clic Timeline au **début du Segment**. L’ADR 0017 reportait le seek à la seconde. En usage, chaque minute produit une interruption visible, et viser un instant précis est impossible.

La 1.1.0 garde le **transport** de l’ADR 0013 (`/get` MediaMTX via l’API, vidéo seule, `Range` Safari) et change le **modèle de lecture** :

- une **Plage enregistrée** est une suite de Segments **contigus** (sans trou) ;
- le lecteur demande une **fenêtre glissante** d’environ **3 minutes** devant la tête (`start` = instant de lecture ou de clic, `duration` courte), renouvelée avant la fin, **bornée** à la plage courante (un trou ne s’englobe pas) — MediaMTX assemble déjà au-delà d’un Segment ;
- un clic sur une plage démarre à la **seconde** visée ; la lecture peut démarrer à l’**image clé** précédente (limite du média, pas une promesse frame-exact) ;
- en lecture, la fin d’une plage **saute** au début de la plage suivante du même jour ; plus de plage → pause (pas de changement de jour automatique) ;
- un clic dans un trou suit le même sens (avant) : début de la plage suivante.

Cette décision remplace la granularité « début de Segment » et l’enchaînement `onEnded` de l’ADR 0013, et lève le report de seek de l’ADR 0017, **sans réécrire** ces ADR.

## Considered Options

- **Une requête = toute la plage** : fluide une fois chargé, mais premier rendu lent et mémoire API élevée (assemblage MP4 pour `Range`).
- **Double buffer Segment par Segment** : garde des requêtes courtes, mais complexité UI et seek mid-segment à part.
- **MSE / playlist** : player riche, coût Safari / tests élevé pour ce job.
- **Fenêtre glissante courte** (retenu) : enchaînement fluide dans une plage, seek réactif, même tuyau `/get`.

## Consequences

- L’UI ne lie plus un `src` à un seul Segment pour la lecture courante ; les helpers regroupent les Plages et calculent `start` / `duration`.
- La cible **~3 min** est produit ; un spike ou ticket peut l’ajuster si latence ou hiccup de renew.
- Zoom Timeline, scrub et lecture inverse restent hors 1.1.0 (candidats feuille de route).
- Export d’une plage reste **1.1.1**.
