#!/usr/bin/env bash
# Construit et pousse les images Site + simulation vers ghcr pour la CI des PR
# (étiquette ARGOS_VERSION, typiquement ci-<sha>, arch du runner seulement).
# Prérequis : docker login ghcr, ARGOS_VERSION non vide.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPOT"

TAG="${ARGOS_VERSION:?ARGOS_VERSION requis (ex. ci-<sha>)}"

# Une image par contexte Docker ; les services Compose qui partagent le tag tirent le même digest.
IMAGES=(
    "ghcr.io/ulyssoulv/argos-api:${TAG}|api"
    "ghcr.io/ulyssoulv/argos-web:${TAG}|web"
    "ghcr.io/ulyssoulv/argos-pont:${TAG}|media"
    "ghcr.io/ulyssoulv/argos-certificats:${TAG}|certificats"
    "ghcr.io/ulyssoulv/argos-temps:${TAG}|temps"
    "ghcr.io/ulyssoulv/argos-camera-simulee:${TAG}|media/simulated"
    "ghcr.io/ulyssoulv/argos-onvif-simule:${TAG}|simulation/onvif"
)

for entree in "${IMAGES[@]}"; do
    etiquette="${entree%%|*}"
    contexte="${entree#*|}"
    echo "=== build+push ${etiquette} ==="
    docker build \
        --label "org.opencontainers.image.source=https://github.com/UlyssouLV/ArgOS" \
        --tag "$etiquette" \
        --build-arg "ARGOS_VERSION=$TAG" \
        "$contexte"
    docker push "$etiquette"
done
