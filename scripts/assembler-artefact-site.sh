#!/usr/bin/env bash
# Archive les fichiers à poser dans /opt/argos (compose, Détection, unité).
# Hors .env, secrets, sources et simulation.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
SORTIE="${1:-${DEPOT}/argos-site.tar.gz}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

DEST="$TMP/argos-site"
mkdir -p "$DEST/scripts/cameras"
cp "$DEPOT/compose.yaml" "$DEST/compose.yaml"
cp "$DEPOT/compose.reseau-cameras.yaml" "$DEST/compose.reseau-cameras.yaml"
cp "$DEPOT/scripts/cameras/configurer-detection.sh" "$DEST/scripts/cameras/configurer-detection.sh"
chmod 755 "$DEST/scripts/cameras/configurer-detection.sh"
cp "$DEPOT/scripts/argos.service" "$DEST/argos.service"

# macOS : ne pas embarquer les fichiers AppleDouble `._*` dans l'archive.
COPYFILE_DISABLE=1 tar -czf "$SORTIE" -C "$TMP" argos-site
echo "Artefact : $SORTIE"
