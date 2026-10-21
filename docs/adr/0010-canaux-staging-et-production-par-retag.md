# Canaux staging et production par retag de digest

Une seule branche `main` : **staging** et **production** sont des **canaux d'images** sur ghcr, pas des forks git. **`:staging`** est l’early access de la version en cours : publié depuis la **branche de version** (skill `/ps`) après `/code-review` et quality gate verts, **avant** les tests humains (`/th`). La promotion vers l'étiquette de version (et optionnellement `:latest`) **retaggue le même digest**, sans rebuild, via le workflow manuel **Promouvoir images vers Release** (une fois Finalise et la Release créés). Les Sites Ubuntu de production suivent le **semver** des Releases (`ARGOS_VERSION=X.Y.Z`), pas `:staging`. Un Site ou une machine perso suit `:staging` pour valider **pendant** `/th` et jusqu’à la promo. Cela affine ADR 0009 (qui opposait surtout Mac local et Sites Ubuntu comme environnements).

## Considered Options

- **Rebuild à chaque Release** : simple, mais le digest prod n'est plus celui validé en staging / `/th`.
- **Deux branches git** (`main` / `production`) : écart de compose et double fusion — déjà rejeté en 0009.
- **Publier `:staging` au push sur `main`** : trop tard pour `/th` (Finalise merge après les humains) et écrase l’early access testé.
- **Sites prod sur `:latest`** : moins de logique, mais version opaque pour le support et le rollback manuel.

## Consequences

- La Release GitHub ne construit pas les images et **ne les promeut plus toute seule** : la promo est un geste conscient (`workflow_dispatch`) une fois `:staging` = digest validé en `/th`.
- `ARGOS_VERSION=staging` sert les Sites / postes de test humains ; un semver sert la prod.
- Multi-arch (`amd64` + `arm64`) pour que machines perso et Sites Ubuntu tirent le même canal.
- Le workflow **Publier images staging** est déclenché à la main / par `/ps` sur la ref de la PR, pas par un push `main`.
