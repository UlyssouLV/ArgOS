#!/usr/bin/env bash
# Lance ArgOS sur macOS : double-clic dans le Finder.
# Démarre Docker Desktop au besoin, puis la stack de dev (mediamtx, api, db, web
# et les Caméras simulées de compose.simulation.yaml), ouvre une fenêtre Terminal
# de logs et l'UI dans le navigateur.
set -u
cd "$(dirname "$0")"

URL_UI="http://localhost:8080"
# Stack de prod + simulation de dev (Caméras simulées).
export COMPOSE_FILE="compose.yaml:compose.simulation.yaml"

pause_et_quitter() {
    echo
    read -n 1 -s -r -p "Appuie sur une touche pour fermer..."
    echo
    exit "$1"
}

valeur_env() {
    sed -n "s/^$1=//p" .env | tail -n 1
}

ecrire_env() {
    local cle="$1" valeur="$2" tmp
    tmp="$(mktemp)"
    awk -v cle="$cle" -v valeur="$valeur" '
        index($0, cle "=") == 1 { print cle "=" valeur; vu = 1; next }
        { print }
        END { if (!vu) print cle "=" valeur }
    ' .env > "$tmp" && mv "$tmp" .env
}

echo "============================================"
echo " Lancement d'ArgOS"
echo "============================================"
echo

echo "[1/4] Configuration (.env)..."
if [ ! -f .env ]; then
    echo "      Première utilisation : création de .env à partir de .env.example."
    cp .env.example .env
fi
if [ -z "$(valeur_env ARGOS_IDENTIFIANT)" ] || [ -z "$(valeur_env ARGOS_MOT_DE_PASSE)" ]; then
    echo "      Le compte de l'Administrateur n'est pas encore défini."
    read -r -p "      Identifiant [administrateur] : " identifiant
    identifiant="${identifiant:-administrateur}"
    read -r -s -p "      Mot de passe (vide = en générer un) : " mot_de_passe
    echo
    if [ -z "$mot_de_passe" ]; then
        mot_de_passe="$(openssl rand -base64 24 | tr '+/' '-_' | tr -d '=\n')"
        echo "      Mot de passe généré (à noter, il est aussi dans .env) : $mot_de_passe"
    fi
    case "$identifiant$mot_de_passe" in
        *[[:space:]\"\'\\]*)
            echo "[ERREUR] Ni espace, ni guillemet, ni antislash dans l'identifiant ou le mot de passe."
            pause_et_quitter 1
            ;;
    esac
    ecrire_env ARGOS_IDENTIFIANT "$identifiant"
    ecrire_env ARGOS_MOT_DE_PASSE "$mot_de_passe"
fi

echo "[2/4] Vérification / démarrage de Docker..."
if ! command -v docker >/dev/null 2>&1; then
    echo "[ERREUR] Docker n'est pas installé (commande « docker » introuvable)."
    echo "         Installe Docker Desktop (voir README.md, Prérequis), puis relance."
    pause_et_quitter 1
fi
if ! docker info >/dev/null 2>&1; then
    if [ ! -d /Applications/Docker.app ]; then
        echo "[ERREUR] Le moteur Docker ne répond pas et Docker.app est introuvable."
        echo "         Ouvre Docker Desktop à la main, attends qu'il soit prêt, puis relance."
        pause_et_quitter 1
    fi
    echo "      Docker Desktop n'est pas lancé : démarrage (une à deux minutes)..."
    open -a Docker
    essais=0
    until docker info >/dev/null 2>&1; do
        essais=$((essais + 1))
        if [ "$essais" -ge 90 ]; then
            echo "[ERREUR] Docker Desktop n'est pas prêt à temps."
            echo "         Attends l'icône Docker dans la barre de menus, puis relance."
            pause_et_quitter 1
        fi
        sleep 2
    done
fi

echo "[3/4] Démarrage de la stack (mediamtx, api, db, web, Caméras simulées)..."
echo "      (premier lancement : construction des images, plusieurs minutes)"
if ! docker compose up -d --build --wait; then
    echo
    echo "[ERREUR] La stack n'a pas démarré. Détail : docker compose logs api"
    pause_et_quitter 1
fi

echo "[4/4] Fenêtre de logs et ouverture de l'UI..."
osascript - "$(pwd)" <<'APPLESCRIPT' >/dev/null
on run argv
    tell application "Terminal"
        do script "cd " & quoted form of (item 1 of argv) & " && COMPOSE_FILE=compose.yaml:compose.simulation.yaml docker compose logs -f --tail 20"
        activate
    end tell
end run
APPLESCRIPT
open "$URL_UI"

echo
echo "ArgOS tourne : UI sur $URL_UI (identifiant et mot de passe dans .env)."
echo "Arrêter : docker compose -f compose.yaml -f compose.simulation.yaml down (fermer les fenêtres ne suffit pas)."
pause_et_quitter 0
