# Inspecter les enregistrements

Les segments d’enregistrement du Site sont des fichiers **fMP4** écrits par le pont MediaMTX, sans réencodage, dans un **volume Docker nommé** `enregistrements` (comme la base et l’Autorité du Site).

Depuis la 0.8.2, la **Relecture** se fait dans l’UI ; depuis la 1.0.0, c’est la page **Relecture** du rail (ou une Caméra du résumé d’**Enregistrement**) : choix de la Caméra et du jour, puis clic sur la timeline de ce jour ([ADR 0017](../adr/0017-conservation-en-jours-et-relecture-a-la-journee.md)) ; seuls les Segments **fermés** se relisent, derrière la session ([ADR 0013](../adr/0013-relecture-des-enregistrements.md)). Le volume n’est plus la seule voie : cette page reste utile en labo, pour voir les fichiers eux-mêmes (pas de téléchargement HTTP).

Arborescence : `camera-<id>/<horodatage…>` (`%path` MediaMTX = le chemin du pont `camera-<id>`). Un segment d’environ une minute ; MediaMTX efface ceux plus vieux que la **Conservation** du Site (1 h par défaut ; réglable de 1 à 24 h depuis la 0.8.1, de 1 h à 30 jours en jours + heures depuis la 1.0.0, [ADR 0017](../adr/0017-conservation-en-jours-et-relecture-a-la-journee.md)).

## 1. Trouver le volume

Le nom Compose est `enregistrements`. Docker y préfixe le projet : `argos_enregistrements` sur un Site Ubuntu (`/opt/argos`), souvent le même préfixe depuis le clone (`ArgOS` → `argos`).

```bash
docker volume ls | grep enregistrements
```

Sur Ubuntu, se placer d’abord dans `/opt/argos`. En hébergement local, à la racine du clone. Si la stack tourne :

```bash
docker inspect -f '{{range .Mounts}}{{if eq .Destination "/enregistrements"}}{{.Name}}{{end}}{{end}}' "$(docker compose -f compose.yaml ps -q mediamtx)"
```

(`-f compose.yaml -f compose.simulation.yaml` en local avec les Caméras simulées.)

## 2. Lister les fichiers

Remplacer `argos_enregistrements` par le nom lu à l’étape 1 :

```bash
docker run --rm -v argos_enregistrements:/enregistrements alpine ls -R /enregistrements
```

Tant qu’aucune Caméra n’enregistre, le volume est vide. Après enregistrement, chaque Caméra a un dossier `camera-<id>/` et des fichiers horodatés (lisibles surtout une fois le segment **fermé**, par exemple dans VLC).

## 3. Ne pas vider le volume par mégarde

`docker compose down -v` (clone ou `/opt/argos`) **efface** ce volume, avec la base et l’Autorité du Site. Pour arrêter sans perdre les fichiers : `docker compose down` sans `-v`.
