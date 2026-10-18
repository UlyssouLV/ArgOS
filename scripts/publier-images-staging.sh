#!/usr/bin/env bash
# Construit et pousse les quatre images du Site vers ghcr, étiquette :staging,
# manifestes linux/amd64 + linux/arm64. Prérequis : docker buildx (QEMU) et login ghcr.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPOT"

PLATEFORMES="linux/amd64,linux/arm64"

publier() {
    local etiquette="$1" contexte="$2"
    docker buildx build \
        --platform "$PLATEFORMES" \
        --provenance=false \
        --label "org.opencontainers.image.source=https://github.com/UlyssouLV/ArgOS" \
        --tag "$etiquette" \
        --push \
        "$contexte"
}

publier ghcr.io/ulyssoulv/argos-api:staging api
publier ghcr.io/ulyssoulv/argos-web:staging web
publier ghcr.io/ulyssoulv/argos-pont:staging media
publier ghcr.io/ulyssoulv/argos-certificats:staging certificats
