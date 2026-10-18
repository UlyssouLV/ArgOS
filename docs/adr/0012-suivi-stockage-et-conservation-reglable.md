# Suivi stockage et conservation réglable sur le volume actuel

L’enregistrement continu (ADR 0011) écrit sur un **volume Docker nommé** avec une conservation fixe. Pour dimensionner la rétention sans changer *où* vivent les octets, le Site expose l’**espace libre** de ce volume, un **seuil** d’alerte (signal seul), une **conservation Site** (1–24 h) poussée en `recordDeleteAfter`, et des **débits d’écriture** mesurés sur les segments récents (repli encodage / inconnu), avec projection « toutes Caméras actives » et estimation de tenue.

## Considered Options

- **Mesures hôte / plusieurs disques dès 0.8.1** : utile en prod, mais autre job (bind, second volume, install) — reporté en **0.8.3** envisagée.
- **Purge ou coupe auto sous le seuil** : filet magique ; hors du job « indications + réglages » ; disque plein reste l’échec d’écriture 0.8.0.
- **Conservation par Caméra** : souplesse, mais curseurs multiples et sync pont plus complexe ; un seul levier Site suffit ici.

## Consequences

- ADR 0011 reste la base (MediaMTX, volume nommé, fMP4) ; seule la conservation cesse d’être une constante figée côté produit.
- L’API lit le même montage `/enregistrements` pour l’espace et les tailles de segments ; elle ne choisit pas un autre disque.
- Le seuil n’arrête pas l’enregistrement ; il informe sur la page **Enregistrement**.
- Bind mount / multi-disque restent hors de cette décision (feuille de route ultérieure).
