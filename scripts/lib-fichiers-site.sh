# Bundle /opt/argos hors .env, secrets et unité systemd.
# Source : dépôt (install, artefact) ou archive de Release (mise à jour).
copier_fichiers_du_site() {
    local source="$1" dest="$2"
    mkdir -p "$dest/scripts/cameras"
    cp "$source/compose.yaml" "$dest/compose.yaml"
    cp "$source/compose.reseau-cameras.yaml" "$dest/compose.reseau-cameras.yaml"
    cp "$source/scripts/cameras/configurer-detection.sh" "$dest/scripts/cameras/configurer-detection.sh"
    chmod 755 "$dest/scripts/cameras/configurer-detection.sh"
    if [ -f "$source/scripts/lib-fichiers-site.sh" ]; then
        cp "$source/scripts/lib-fichiers-site.sh" "$dest/scripts/lib-fichiers-site.sh"
    fi
    if [ -f "$source/scripts/mettre-a-jour-le-site.sh" ]; then
        cp "$source/scripts/mettre-a-jour-le-site.sh" "$dest/scripts/mettre-a-jour-le-site.sh"
        chmod 755 "$dest/scripts/mettre-a-jour-le-site.sh"
    fi
}
