#!/usr/bin/env bash
# Archive les fichiers à poser dans /opt/argos (compose, Détection, unité).
# Hors .env, secrets, sources et simulation.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
SORTIE="${1:-${DEPOT}/argos-site.tar.gz}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# shellcheck source=lib-fichiers-site.sh
. "$(dirname "$0")/lib-fichiers-site.sh"

DEST="$TMP/argos-site"
copier_fichiers_du_site "$DEPOT" "$DEST"
cp "$DEPOT/scripts/argos.service" "$DEST/argos.service"

# macOS : ne pas embarquer les fichiers AppleDouble `._*` dans l'archive.
COPYFILE_DISABLE=1 tar -czf "$SORTIE" -C "$TMP" argos-site
echo "Artefact : $SORTIE"
