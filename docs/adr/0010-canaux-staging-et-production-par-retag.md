# Canaux staging et production par retag de digest

Une seule branche `main` : **staging** et **production** sont des **canaux d'images** sur ghcr, pas des forks git. La CI verte sur `main` publie le digest sous `:staging` ; une GitHub Release `vX.Y.Z` **promouvoit** le même digest vers l'étiquette de version (et optionnellement `:latest`), sans rebuild. Les Sites Ubuntu de production suivent le semver des Releases ; un Site ou une machine perso peut suivre `:staging` pour valider avant la promotion. Cela affine ADR 0009 (qui opposait surtout Mac local et Sites Ubuntu comme environnements).

## Considered Options

- **Rebuild à chaque Release** : simple, mais le digest prod n'est plus celui validé en staging / CI.
- **Deux branches git** (`main` / `production`) : écart de compose et double fusion — déjà rejeté en 0009.
- **Sites prod sur `:latest`** : moins de logique, mais version opaque pour le support et le rollback manuel.

## Consequences

- La Release ne construit pas : elle retaggue.
- `ARGOS_VERSION=staging` (ou équivalent documenté) sert les Sites / postes de test ; un semver sert la prod.
- Multi-arch (`amd64` + `arm64`) pour que machines perso et Sites Ubuntu tirent le même canal.
