# Conservation en jours et Relecture à la journée

L’ADR 0012 bornait la **Conservation** du Site à 1–24 h, et l’ADR 0013 faisait couvrir à la **Timeline d’enregistrement** toute la Conservation, la liste des Segments fermés venant d’un seul appel (`GET /api/cameras/<id>/segments`). Une vidéosurveillance domestique garde couramment une semaine ou plus.

La 1.0.0 porte la Conservation à **1 h – 30 jours** (720 h). Le stockage reste en **heures** (`conservation_h`, pas de migration ; `recordDeleteAfter` déjà en heures) ; l’UI la saisit en **jours + heures** et l’affiche « 7 j », « 2 j 6 h », « 12 h ». La tenue disque de l’ADR 0012 s’applique telle quelle.

Sur 30 jours, des Segments d’environ une minute font des dizaines de milliers de plages : une Timeline unique serait illisible et le clic imprécis. La Relecture montre donc **un jour à la fois** (jour civil dans le fuseau de l’Heure du Site, ADR 0014), avec un sélecteur de jour ; l’API rend les Segments d’un jour (`?jour=AAAA-MM-JJ`) et la fenêtre de Conservation pour griser les autres jours. Le clic garde la granularité de l’ADR 0013 (début du Segment).

Cette décision remplace la borne 1–24 h de l’ADR 0012 et la Timeline « toute la Conservation » de l’ADR 0013, sans les réécrire. Le seek à la seconde annoncé par l’ADR 0013 pour la 1.0.0 est reporté (Plus tard).

## Considered Options

- **Timeline unique sur toute la Conservation** : simple, mais inutilisable au-delà de quelques jours, et une réponse API de milliers de Segments.
- **Timeline zoomable (30 jours → 1 heure)** : la plus riche, mais un composant lourd (molette, niveaux, chargement par fenêtre) qui tient d’une nouvelle fonction, hors du job « refonte graphique ».
- **Un jour à la fois** (retenu) : précision du clic inchangée, réponse API bornée, usage habituel des enregistreurs vidéo.
- **Maximum au-delà de 30 jours** : possible techniquement, mais le volume Docker actuel (ADR 0012) n’a pas de stockage dédié ; la tenue disque avertit déjà quand le réglage est trop ambitieux.

## Consequences

- `CONSERVATION_MAX` passe à 720 côté API et UI.
- `GET /api/cameras/<id>/segments` accepte `jour` ; sans ce paramètre, il rend le jour courant (plus toute la Conservation).
- Un jour de changement d’heure fait 23 ou 25 h : la Timeline suit la durée réelle du jour dans le fuseau du Site.
