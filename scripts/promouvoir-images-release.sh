#!/usr/bin/env bash
# Promouvoit le digest :staging vers l'étiquette de Release X.Y.Z et :latest,
# sans rebuild (copie de manifeste). Prérequis : docker buildx et login ghcr.
# Déclenché à la main (workflow « Promouvoir images vers Release ») : ARGOS_RELEASE_TAG=vX.Y.Z.
set -euo pipefail

ETIQUETTE="${ARGOS_RELEASE_TAG:-${GITHUB_REF_NAME:-}}"
if [[ ! "$ETIQUETTE" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[ERREUR] Étiquette de Release attendue vX.Y.Z, reçu : ${ETIQUETTE}." >&2
    exit 1
fi
VERSION="${ETIQUETTE#v}"

# Commit de la Release : celui du tag (déréférencé s'il est annoté).
SHA_RELEASE="${ARGOS_RELEASE_SHA:-}"
if [ -z "$SHA_RELEASE" ]; then
    REFS="$(git ls-remote origin "refs/tags/$ETIQUETTE" "refs/tags/$ETIQUETTE^{}")"
    SHA_RELEASE="$(awk '/\^\{\}$/ { print $1; exit }' <<<"$REFS")"
    SHA_RELEASE="${SHA_RELEASE:-$(awk 'NR == 1 { print $1 }' <<<"$REFS")}"
fi
if [ -z "$SHA_RELEASE" ]; then
    echo "[ERREUR] Tag $ETIQUETTE introuvable sur origin." >&2
    exit 1
fi

# :staging doit avoir été construit depuis ce commit (/ps sur la branche de version), sinon la Release
# porterait les images d'une version précédente.
revision_staging() {
    docker buildx imagetools inspect "ghcr.io/ulyssoulv/argos-$1:staging" --format '{{json .Image}}' |
        python3 -c '
import json, sys
image = json.load(sys.stdin)
plateformes = image.values() if "config" not in image else [image]
revisions = {(p.get("config") or {}).get("Labels", {}).get("org.opencontainers.image.revision", "") for p in plateformes}
print(revisions.pop() if len(revisions) == 1 else "")
'
}

for image in api web pont certificats temps; do
    REVISION="$(revision_staging "$image")"
    if [ "$REVISION" != "$SHA_RELEASE" ]; then
        echo "[ERREUR] argos-$image:staging construit depuis « ${REVISION:-commit inconnu} », pas depuis $SHA_RELEASE ($ETIQUETTE). Lancer « Publier images staging » sur $ETIQUETTE, puis relancer la promotion." >&2
        exit 1
    fi
done

promouvoir() {
    local image="$1"
    docker buildx imagetools create \
        --tag "ghcr.io/ulyssoulv/argos-${image}:${VERSION}" \
        --tag "ghcr.io/ulyssoulv/argos-${image}:latest" \
        "ghcr.io/ulyssoulv/argos-${image}:staging"
}

for image in api web pont certificats temps; do
    promouvoir "$image"
done
