# Détection depuis le réseau bridge : sous-réseaux déclarés

La Détection des Caméras part du conteneur `api`, qui reste sur le réseau bridge de Docker. Depuis là, il joint les adresses du réseau local par NAT, mais il ne voit ni les prises réseau de la machine hôte, ni leurs sous-réseaux, ni les adresses MAC des appareils. Les sous-réseaux à balayer sont donc **déclarés** dans `ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX`, recalculés à chaque lancement par un script lancé sur l'hôte à partir de la ou des prises retenues pour les caméras.

## Considered Options

- **`network_mode: host` pour `api`** : l'API verrait les prises, les sous-réseaux et la table ARP (donc les MAC). Écarté : `api` perd les noms Compose (`db`, `mediamtx`), le port de l'API s'expose sur toutes les interfaces sans passer par Compose, et Docker Desktop (dev sur Mac) ne se comporte pas comme Docker Engine sous Linux.
- **Saisie des sous-réseaux dans l'Administration** : reportée à « Configuration initiale du Site » (feuille de route) ; un script hôte suffit pour la 0.4.0 et suit les changements d'adresse à chaque lancement.

## Consequences

- La 0.4.2 (identité stable par adresse MAC) ne pourra pas lire la MAC depuis `api` en bridge : il faudra l'obtenir autrement (hôte, caméra elle-même, ONVIF…).
- Les Caméras simulées vivent sur leur propre réseau Compose, déclaré par le fichier Compose de simulation, qui ajoute lui-même son sous-réseau : le script hôte n'en sait rien et la prod n'en garde aucune trace.
