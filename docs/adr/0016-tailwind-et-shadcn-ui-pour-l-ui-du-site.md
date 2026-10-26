# Tailwind et shadcn/ui pour l’UI du Site

Jusqu’à la 0.9.x, l’UI React du Site (`web/`) est stylée par une seule feuille `styles.css` écrite à la main, sans tokens ni composants partagés : chaque version a ajouté ses classes, et l’interface n’a pas d’identité. La 1.0.0 la redessine entièrement (identité validée sur maquette : thème sombre, rouge du logo en accent, Inter / JetBrains Mono).

On reprend la technique du dépôt BBASS (`poste/frontend`) : **Tailwind v4** (`@tailwindcss/vite`) et **shadcn/ui** (style new-york) — des composants **copiés dans le dépôt** (`web/src/components/ui/`) au-dessus de **Radix**, avec **lucide-react** (icônes), **sonner** (toasts), `class-variance-authority`, `clsx` et `tailwind-merge`. L’identité vit dans des **variables CSS** sur `:root`, exposées à Tailwind par `@theme inline`. Les polices sont **embarquées** (woff2 dans `web/src/assets/fonts/`) : un Site sur réseau local peut n’avoir aucun accès Internet.

Écart avec BBASS : les versions sont **exactes** dans `package.json` (pas de `^`), comme le reste d’ArgOS.

## Considered Options

- **CSS pur + tokens** : aucune dépendance, mais panneau latéral, boîte de dialogue, onglets, listes déroulantes et toasts accessibles seraient à réécrire (focus piégé, Échap, ARIA) ; c’est ce que Radix fournit.
- **Bibliothèque de composants packagée (MUI, Mantine…)** : composants prêts mais style imposé et difficile à plier à l’identité ; mise à jour en bloc.
- **Tailwind + shadcn/ui** (retenu) : même pile que BBASS (un seul savoir-faire pour le mainteneur), composants possédés par le dépôt et modifiables, accessibilité Radix, tokens centralisés.

## Consequences

- Toute nouvelle UI utilise les composants de `web/src/components/ui/` et les tokens ; pas de couleur ni de taille en dur hors des tokens.
- `styles.css` disparaît ; les tests web visent rôles et libellés, jamais des classes Tailwind.
- Un composant shadcn/ui ajouté plus tard est copié (CLI ou à la main) puis versionné comme du code ArgOS ; ses dépendances Radix sont épinglées à la version exacte.
- Le build web gagne Tailwind (temps de build et taille CSS négligeables, CSS purgé à la compilation).
