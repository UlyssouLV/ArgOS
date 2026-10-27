# Relecture continue : fenêtre glissante et seek à la seconde

L’ADR 0013 livrait la Relecture Segment par Segment (`src` = un Segment, `onEnded` → suivant) et un clic Timeline au **début du Segment**. L’ADR 0017 reportait le seek à la seconde. En usage, chaque minute produit une interruption visible, et viser un instant précis est impossible.

La 1.1.0 garde le **transport** de l’ADR 0013 (`/get` MediaMTX via l’API, vidéo seule, `Range` Safari) et change le **modèle de lecture** :

- une **Plage enregistrée** est une suite de Segments **contigus** (sans trou) ;
- le lecteur demande une **fenêtre glissante** devant la tête (`start` = instant de lecture ou de clic), renouvelée avant la fin, **bornée** à la plage courante (un trou ne s’englobe pas) ; depuis #172, elle s’arrête aussi à la fin de son **Segment** (voir « Un Segment par fenêtre ») ;
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
- Le renouvellement se fait avant la fin par **préchargement** : à ~30 s de temps réel de la fin (vitesse comprise), la fenêtre suivante se charge dans une seconde `<video>` cachée, qui prend le relais à la fin, sans nouveau `src` sur la vidéo à l’écran (#167). La suite est figée à sa demande : un rafraîchissement de la Timeline qui allonge la Plage ne la redemande pas avant le relais.
- Un reste de Segment de moins d’une seconde n’est pas demandé au Pont : la fenêtre part du début du Segment suivant de la Plage, ou de la Plage suivante.
- Après la dernière Plage du jour, la lecture ne reprend seule que si un Segment fermé depuis prolonge cette Plage ; une Plage apparue plus loin attend un clic.
- La cible **~3 min** de la 1.1.0 a cédé la place à un Segment par fenêtre (#172) : environ 1 min, la durée des Segments du Pont.
- Zoom Timeline, scrub et lecture inverse restent hors 1.1.0 (candidats feuille de route).
- Export d’une plage reste **1.1.1**.

## Un Segment par fenêtre (#172)

Sur Cam 01 (H.265 et audio G711), Chrome levait `PIPELINE_ERROR_DECODE` (VideoToolbox `-12909`) à chaque passage d’un Segment au suivant d’une fenêtre. Cause, relevée dans les Segments et les journaux du Pont :

- la caméra horodate son audio en avance d’environ 14 s sur sa vidéo, écart qui varie au fil de la session RTSP ; MediaMTX ouvre alors chaque Segment à l’heure de l’audio et jette la vidéo arrivée « trop tard » (`sample of track … received too late, discarding`), image clé comprise ;
- chaque Segment perd ainsi ~14 s de vidéo à son début (61,7 s de vidéo pour 76 s d’heure réelle), et sa vidéo commence par des images P ;
- le `/get` de MediaMTX, qui assemble plusieurs Segments dans un MP4, met ces images P juste après la dernière image du Segment précédent : le décodeur matériel les refuse. Lues seules, depuis une nouvelle `<video>`, elles passent.

Décisions :

- **Une fenêtre ne dépasse jamais la fin de son Segment**, bornée au début du suivant (la dernière écriture d’un fichier peut le dépasser) : MediaMTX n’assemble plus de Segments. Le passage au Segment suivant se fait par la suite préchargée (#167).
- **L’API recale le début de la fenêtre** sur la vidéo du Segment : la vidéo finit à la fin réelle du Segment, le début de la fenêtre recule donc de l’écart entre heure réelle et vidéo (au-delà d’une seconde), sans passer avant le Segment. Sa fin ne bouge pas : l’audio, en avance, précède la vidéo dans le fichier, et MediaMTX s’arrête au premier échantillon, toutes pistes confondues, qui dépasse la fenêtre. Sans ce recalage, l’image lue avait ~16 s d’avance sur l’instant visé, et un clic dans les ~14 dernières secondes d’un Segment ne trouvait plus de vidéo.
- **L’instant lu suit l’image** : la vidéo servie finit avec la fenêtre ; plus courte qu’elle (clic dans la vidéo perdue au début d’un Segment), elle commence d’autant plus tard.

Limites restantes :

- la vidéo jetée à l’enregistrement est perdue : la lecture saute ces ~14 s au passage d’un Segment au suivant, et l’instant lu avec elle ;
- un clic dans cette vidéo perdue part de la première image du Segment, plus tard que l’instant visé ;
- l’horloge propre à la caméra (moins de 2 s d’écart au Live) et l’image clé de départ restent visibles dans l’heure incrustée.

Corriger l’enregistrement (ne garder que la vidéo, ou réaligner les pistes) relève du Pont, hors de cette décision.

En dev, `camera-simulee-6` reproduit ce cas (#173, `media/simulated/README.md`) : son audio prend ~14 s d’avance sur sa vidéo pendant la lecture du Pont.
