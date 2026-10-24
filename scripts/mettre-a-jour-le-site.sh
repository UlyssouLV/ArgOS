#!/usr/bin/env bash
# Détecte une GitHub Release semver plus récente et l'applique au Site Ubuntu.
# Codes : 0 appliquée, 2 rien à faire, 1 échec (journalisé, pas de rollback).
set -euo pipefail

CODE_RIEN=2
PREFIXE="${ARGOS_PREFIX:-}"
RACINE="${PREFIXE}/opt/argos"
FICHIER_ENV="$RACINE/.env"
DEPOT_GITHUB="${ARGOS_GITHUB_DEPOT:-UlyssouLV/ArgOS}"
UNITE="${PREFIXE}/etc/systemd/system/argos.service"

echec() {
    echo "[ERREUR] $1" >&2
    exit 1
}

valeur_env() {
    sed -n "s/^$1=//p" "$FICHIER_ENV" | tail -n 1
}

ecrire_env() {
    local cle="$1" valeur="$2" tmp
    tmp="$(mktemp)"
    awk -v cle="$cle" -v valeur="$valeur" '
        index($0, cle "=") == 1 { print cle "=" valeur; vu = 1; next }
        { print }
        END { if (!vu) print cle "=" valeur }
    ' "$FICHIER_ENV" > "$tmp" && mv "$tmp" "$FICHIER_ENV"
}

# Repli de `temps` sur l'horloge du serveur : l'OS de l'hôte reste synchronisé en NTP (ADR 0015).
synchroniser_l_hote_en_ntp() {
    if ! command -v timedatectl >/dev/null 2>&1; then
        echo "timedatectl introuvable : synchro NTP de l'hôte non vérifiée."
        return 0
    fi
    if [ "$(timedatectl show -p NTP 2>/dev/null)" != "NTP=no" ]; then
        return 0
    fi
    if timedatectl set-ntp true; then
        echo "Synchro NTP de l'hôte réactivée (timedatectl set-ntp true)."
    else
        echo "[ATTENTION] timedatectl set-ntp true a échoué : synchro NTP de l'hôte toujours coupée." >&2
    fi
}

synchroniser_l_hote_en_ntp

if [ ! -f "$FICHIER_ENV" ]; then
    echec "Fichier .env introuvable dans $RACINE."
fi

VERSION_LOCALE="$(valeur_env ARGOS_VERSION)"
if [[ ! "$VERSION_LOCALE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "ARGOS_VERSION=$VERSION_LOCALE n'est pas un semver de production : rien à faire."
    exit "$CODE_RIEN"
fi

command -v curl >/dev/null 2>&1 || echec "curl introuvable."
command -v python3 >/dev/null 2>&1 || echec "python3 introuvable."

RELEASES="$(
    curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 \
        -H "Accept: application/vnd.github+json" \
        -H "User-Agent: argos-site" \
        "https://api.github.com/repos/${DEPOT_GITHUB}/releases"
)" || echec "Impossible de lister les Releases GitHub."

CHOIX="$(
    printf '%s' "$RELEASES" | python3 -c '
import json, re, sys

local = sys.argv[1]
pat = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

def parse(tag: str):
    m = pat.match(tag or "")
    return tuple(int(p) for p in m.groups()) if m else None

local_t = parse(local)
if local_t is None:
    sys.exit(2)

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
if not isinstance(data, list):
    sys.exit(1)

best = None
url = None
for rel in data:
    if rel.get("prerelease"):
        continue
    tag_t = parse(str(rel.get("tag_name") or ""))
    if tag_t is None or tag_t <= local_t:
        continue
    asset_url = None
    for asset in rel.get("assets") or []:
        if asset.get("name") == "argos-site.tar.gz":
            asset_url = asset.get("browser_download_url")
            break
    if best is None or tag_t > best:
        best = tag_t
        url = asset_url

if best is None:
    print("RIEN")
    sys.exit(0)
if not url:
    sys.exit(1)
print(f"{best[0]}.{best[1]}.{best[2]} {url}")
' "$VERSION_LOCALE"
)" || echec "Impossible de comparer les Releases semver."

if [ "$CHOIX" = "RIEN" ]; then
    echo "Site déjà à jour (ARGOS_VERSION=$VERSION_LOCALE)."
    exit "$CODE_RIEN"
fi

VERSION_CIBLE="${CHOIX%% *}"
URL_ARTEFACT="${CHOIX#* }"
[ -n "$VERSION_CIBLE" ] && [ -n "$URL_ARTEFACT" ] || echec "Release semver sans artefact."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 \
    -o "$TMP/argos-site.tar.gz" "$URL_ARTEFACT" || echec "Téléchargement de l'artefact impossible."
tar -xzf "$TMP/argos-site.tar.gz" -C "$TMP" || echec "Archive d'artefact illisible."
SRC="$TMP/argos-site"
[ -d "$SRC" ] || echec "Artefact sans dossier argos-site."

# shellcheck source=lib-fichiers-site.sh
. "$(dirname "$0")/lib-fichiers-site.sh"
copier_fichiers_du_site "$SRC" "$RACINE"
if [ -f "$SRC/argos.service" ]; then
    cp "$SRC/argos.service" "$RACINE/argos.service"
    if [ -d "$(dirname "$UNITE")" ]; then
        cp "$SRC/argos.service" "$UNITE"
        if command -v systemctl >/dev/null 2>&1; then
            systemctl daemon-reload || true
        fi
    fi
fi

ecrire_env ARGOS_VERSION "$VERSION_CIBLE"
chmod 640 "$FICHIER_ENV" || true

if getent passwd argos >/dev/null 2>&1; then
    chown -R argos:argos "$RACINE" || true
fi

(
    cd "$RACINE"
    docker compose pull
) || echec "docker compose pull a échoué (pas de rollback automatique)."
(
    cd "$RACINE"
    docker compose up -d --wait --force-recreate
) || echec "Recreate Compose a échoué (pas de rollback automatique)."

echo "Site mis à jour vers $VERSION_CIBLE."
