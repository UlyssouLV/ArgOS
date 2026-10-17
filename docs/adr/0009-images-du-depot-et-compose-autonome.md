# Images du dépôt et compose autonome, une seule branche

Le Site doit pouvoir tourner sans clonage, avec des images nommées d'après **ce** dépôt, tout en gardant une seule histoire git. Nous étiquetons `api`, `web`, `pont` et `certificats` en `ghcr.io/ulyssoulv/argos-…:${ARGOS_VERSION}` dès la 0.7.0 (publication au registre en 0.7.2), et le compose de prod à la racine porte à la fois `image:` et `build:`. `main` reste l'unique branche source : staging et production sont des **environnements** (Mac local vs Sites Ubuntu) et, plus tard, une promotion d'image déjà verte — pas un git production allégé.

## Considered Options

- **Deux branches** (`main` / staging avec toutes les sources, `production` sans `api/` ni `web/`) : l'installateur ne voit que le compose, mais le compose et les scripts divergent, et chaque correctif se fusionne deux fois.
- **Registre et `docker pull` dès 0.7.0** : le Site Ubuntu n'a plus besoin de `save` / `load`, mais la publication des images est le job de la 0.7.2 (après la CI des PR en 0.7.1).
- **Noms d'images locaux** (`argos-api:0.7.0`) puis renommage GHCR en 0.7.2 : le compose d'Ubuntu changerait au moment de la publication.

## Consequences

- Ubuntu n'a dans `/opt/argos` que le projet Compose ; l'API et l'UI s'exécutent dans les conteneurs.
- Un `compose up --build` depuis le clone étiquette déjà les noms du futur registre.
- La 0.7.2 pousse les mêmes tags et remplace `save` / `load` par `pull` ; une promotion (même digest) n'exige pas de seconde branche.
