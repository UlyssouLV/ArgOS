# Checks requis sur `main`

Protéger `main` dans **Settings** GitHub (règle de branche, à la main — pas d’API) :

1. Exiger le check **`ArgOS tests / ArgOS tests`** (nom affiché par GitHub : workflow `ArgOS tests`, job `ArgOS tests`).
2. Ajouter à cette liste toute CI ajoutée plus tard.

Tant qu’un check requis est rouge, la PR ne se fusionne pas.
