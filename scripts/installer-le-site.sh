#!/usr/bin/env bash
# Pose un Site sur Ubuntu : dossier Compose /opt/argos, compte argos, unité systemd.
# Sans clone dans le dossier installé : compose de prod, .env du Site, script de Détection.
# Images du Site par docker compose pull (registre ghcr). Pas de Caméras simulées.
# Voir docs/adr/0009-images-du-depot-et-compose-autonome.md.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIXE="${ARGOS_PREFIX:-}"
RACINE="${PREFIXE}/opt/argos"
UNITE="${PREFIXE}/etc/systemd/system/argos.service"
FICHIER_ENV="$RACINE/.env"

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

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERREUR] Docker n'est pas installé (commande « docker » introuvable)." >&2
    exit 1
fi

if [ ! -f "$DEPOT/compose.yaml" ] || [ ! -f "$DEPOT/.env.example" ]; then
    echo "[ERREUR] compose.yaml ou .env.example introuvable à côté du script ($DEPOT)." >&2
    exit 1
fi

# shellcheck source=lib-fichiers-site.sh
. "$(dirname "$0")/lib-fichiers-site.sh"

# `certificats/` : bind Compose du certificat fourni (`create_host_path: false`). Vide = Autorité du Site.
mkdir -p "$RACINE/certificats" "$(dirname "$UNITE")"
copier_fichiers_du_site "$DEPOT" "$RACINE"

if [ ! -f "$FICHIER_ENV" ]; then
    awk '
        /^# SonarCloud/ { next }
        /^SONAR_/ { next }
        { print }
    ' "$DEPOT/.env.example" > "$FICHIER_ENV"
fi

if [ -z "$(valeur_env ARGOS_IDENTIFIANT)" ] || [ -z "$(valeur_env ARGOS_MOT_DE_PASSE)" ]; then
    identifiant="${ARGOS_IDENTIFIANT:-}"
    mot_de_passe="${ARGOS_MOT_DE_PASSE:-}"
    if [ -z "$identifiant" ] || [ -z "$mot_de_passe" ]; then
        if [ ! -t 0 ]; then
            echo "[ERREUR] Compte de l'Administrateur manquant : ARGOS_IDENTIFIANT et ARGOS_MOT_DE_PASSE, ou un terminal." >&2
            exit 1
        fi
        echo "Compte de l'Administrateur du Site."
        read -r -p "Identifiant [administrateur] : " identifiant
        identifiant="${identifiant:-administrateur}"
        read -r -s -p "Mot de passe : " mot_de_passe
        echo
        if [ -z "$mot_de_passe" ]; then
            echo "[ERREUR] Mot de passe vide." >&2
            exit 1
        fi
    fi
    ecrire_env ARGOS_IDENTIFIANT "$identifiant"
    ecrire_env ARGOS_MOT_DE_PASSE "$mot_de_passe"
fi

chmod 640 "$FICHIER_ENV"

( cd "$RACINE" && docker compose pull )

if ! getent group docker >/dev/null; then
    echo "[ERREUR] Groupe docker introuvable : installe Docker, puis relance." >&2
    exit 1
fi
if ! getent passwd argos >/dev/null; then
    useradd --system --home /opt/argos --shell /usr/sbin/nologin --no-create-home argos
fi
usermod -aG docker argos
chown -R argos:argos "$RACINE"
chmod 750 "$RACINE"

cp "$DEPOT/scripts/argos.service" "$UNITE"

systemctl daemon-reload
systemctl enable --now argos.service
echo "Site installé dans /opt/argos (unité argos.service)."
