# Checks requis sur `main`

Protéger `main` dans **Settings** GitHub (règle de branche, à la main — pas d’API) :

1. Exiger le check **`ArgOS tests`** (job agrégateur ; workflow et job portent le même libellé). Les suites enfants (`tests/api/`, `tests/web/`, …) apparaissent dans Actions mais ne sont pas des checks requis.
2. Ajouter à cette liste toute CI ajoutée plus tard (hors jobs enfants du même workflow).

Tant qu’un check requis est rouge, la PR ne se fusionne pas.

Relance ciblée hors PR : **Actions** → **ArgOS tests** → **Run workflow** → choisir une suite (`tests/api/`, …) ou `all`.
