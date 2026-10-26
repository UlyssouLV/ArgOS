#!/usr/bin/env bash
# Construit et pousse les images du Site vers ghcr, étiquette :staging,
# manifestes linux/amd64 + linux/arm64. Prérequis : docker buildx (QEMU) et login ghcr.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPOT"

PLATEFORMES="linux/amd64,linux/arm64"
# Version affichée par l'UI : X.Y.Z de la branche de version (vX.Y.Z-…), le digest :staging étant promu
# tel quel vers la Release.
BRANCHE="${GITHUB_REF_NAME:-$(git branch --show-current)}"
VERSION="$(sed -nE 's/^v([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' <<<"$BRANCHE")"
VERSION="${VERSION:-staging}"

publier() {
    local etiquette="$1" contexte="$2"
    docker buildx build \
        --platform "$PLATEFORMES" \
        --provenance=false \
        --label "org.opencontainers.image.source=https://github.com/UlyssouLV/ArgOS" \
        --tag "$etiquette" \
        --build-arg "ARGOS_VERSION=$VERSION" \
        --push \
        "$contexte"
}

publier ghcr.io/ulyssoulv/argos-api:staging api
publier ghcr.io/ulyssoulv/argos-web:staging web
publier ghcr.io/ulyssoulv/argos-pont:staging media
publier ghcr.io/ulyssoulv/argos-certificats:staging certificats
publier ghcr.io/ulyssoulv/argos-temps:staging temps
