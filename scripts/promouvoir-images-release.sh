#!/usr/bin/env bash
# Promouvoit le digest :staging vers l'étiquette de Release X.Y.Z et :latest,
# sans rebuild (copie de manifeste). Prérequis : docker buildx et login ghcr.
# Déclenché par une GitHub Release taguée vX.Y.Z (GITHUB_REF_NAME).
set -euo pipefail

ETIQUETTE="${GITHUB_REF_NAME:-}"
if [[ ! "$ETIQUETTE" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[ERREUR] Étiquette de Release attendue vX.Y.Z, reçu : ${ETIQUETTE}." >&2
    exit 1
fi
VERSION="${ETIQUETTE#v}"

promouvoir() {
    local image="$1"
    docker buildx imagetools create \
        --tag "ghcr.io/ulyssoulv/argos-${image}:${VERSION}" \
        --tag "ghcr.io/ulyssoulv/argos-${image}:latest" \
        "ghcr.io/ulyssoulv/argos-${image}:staging"
}

for image in api web pont certificats; do
    promouvoir "$image"
done
