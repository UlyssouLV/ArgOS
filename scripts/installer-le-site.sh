#!/usr/bin/env bash
# Pose un Site sur Ubuntu : dossier Compose /opt/argos, compte argos, unité systemd.
# Sans clone dans le dossier installé : compose de prod, .env du Site, script de Détection.
# Les images du Site doivent déjà être chargées (docker load). Pas de Caméras simulées.
# Voir docs/adr/0009-images-du-depot-et-compose-autonome.md.
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
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

if [ ! -f "$SOURCE/compose.yaml" ] || [ ! -f "$SOURCE/.env.example" ]; then
    echo "[ERREUR] compose.yaml ou .env.example introuvable à côté du script ($SOURCE)." >&2
    exit 1
fi

mkdir -p "$RACINE/scripts/cameras" "$(dirname "$UNITE")"
cp "$SOURCE/compose.yaml" "$RACINE/compose.yaml"
cp "$SOURCE/compose.reseau-cameras.yaml" "$RACINE/compose.reseau-cameras.yaml"
cp "$SOURCE/scripts/cameras/configurer-detection.sh" "$RACINE/scripts/cameras/configurer-detection.sh"
chmod 755 "$RACINE/scripts/cameras/configurer-detection.sh"

if [ ! -f "$FICHIER_ENV" ]; then
    awk '
        /^# SonarCloud/ { next }
        /^SONAR_/ { next }
        { print }
    ' "$SOURCE/.env.example" > "$FICHIER_ENV"
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

cat > "$UNITE" <<'EOF'
[Unit]
Description=ArgOS
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=argos
WorkingDirectory=/opt/argos
# « - » : un échec du script (plage trop grande) n'empêche pas ArgOS de démarrer.
ExecStartPre=-/opt/argos/scripts/cameras/configurer-detection.sh
ExecStart=/usr/bin/docker compose up -d --wait
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now argos.service
echo "Site installé dans /opt/argos (unité argos.service)."
