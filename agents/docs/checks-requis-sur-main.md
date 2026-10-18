# Checks requis sur `main`

Protéger `main` dans **Settings** GitHub (règle de branche, à la main — pas d’API) :

1. Exiger le check **`ArgOS tests`** (nom affiché par GitHub pour la protection de branche ; workflow et job portent le même libellé).
2. Ajouter à cette liste toute CI ajoutée plus tard.

Tant qu’un check requis est rouge, la PR ne se fusionne pas.
