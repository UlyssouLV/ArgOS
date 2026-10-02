#!/usr/bin/env bash
# Configure la Détection des Caméras, sur la machine hôte (Linux : ip, macOS : ifconfig).
# Premier lancement en terminal : demande la ou les prises qui relient les caméras (aucune question
# s'il n'y en a qu'une) et les retient dans .env (ARGOS_DETECTION_CAMERAS_INTERFACES).
# Chaque lancement : recalcule le(s) sous-réseau(x) de ces prises et les écrit dans .env
# (ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX). Sans terminal (démarrage automatique) : aucune question.
# Voir ADR 0002. Fichier .env : ARGOS_FICHIER_ENV, sinon celui de la racine du dépôt.
set -u

RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
FICHIER_ENV="${ARGOS_FICHIER_ENV:-$RACINE/.env}"
CLE_INTERFACES=ARGOS_DETECTION_CAMERAS_INTERFACES
CLE_SOUS_RESEAUX=ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX
# Même plafond que l'API : au-delà, une Détection ne tiendrait pas en une dizaine de secondes.
PLAFOND=1024

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

# Une ligne « prise adresse préfixe » par adresse IPv4 de la machine.
adresses() {
    case "$(uname -s)" in
        Linux)
            ip -o -4 addr show | awk '{ split($4, a, "/"); print $2, a[1], a[2] }'
            ;;
        Darwin)
            ifconfig | awk '
                /^[^ \t]/ { prise = $1; sub(/:$/, "", prise) }
                $1 == "inet" { for (i = 3; i < NF; i++) if ($i == "netmask") print prise, $2, $(i + 1) }
            ' | while read -r prise adresse masque; do
                echo "$prise $adresse $(prefixe_du_masque "$masque")"
            done
            ;;
        *)
            echo "[ERREUR] Système non pris en charge : $(uname -s) (Linux ou macOS)." >&2
            exit 1
            ;;
    esac
}

prefixe_du_masque() {
    local masque=$(($1)) prefixe=0
    while [ $((masque & 0x80000000)) -ne 0 ]; do
        prefixe=$((prefixe + 1))
        masque=$(((masque << 1) & 0xffffffff))
    done
    echo "$prefixe"
}

# Boucle locale, Docker et 169.254.0.0/16 écartés ; seules les adresses privées restent.
prise_candidate() {
    local prise="$1" adresse="$2"
    case "$prise" in
        lo | lo0 | docker0 | br-* | veth*) return 1 ;;
    esac
    case "$adresse" in
        10.* | 192.168.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) return 0 ;;
    esac
    return 1
}

sous_reseau() {
    local adresse="$1" prefixe="$2" a b c d entier masque
    IFS=. read -r a b c d <<< "$adresse"
    entier=$(((a << 24) | (b << 16) | (c << 8) | d))
    masque=$(((0xffffffff << (32 - prefixe)) & 0xffffffff))
    entier=$((entier & masque))
    echo "$((entier >> 24 & 255)).$((entier >> 16 & 255)).$((entier >> 8 & 255)).$((entier & 255))/$prefixe"
}

# Une ligne « prise sous-réseau » par adresse candidate.
candidats() {
    adresses | while read -r prise adresse prefixe; do
        if prise_candidate "$prise" "$adresse"; then
            echo "$prise $(sous_reseau "$adresse" "$prefixe")"
        fi
    done
}

sous_reseaux_de() {
    awk -v prise="$1" '$1 == prise { print $2 }' <<< "$CANDIDATS"
}

choisir_prises() {
    local prises=() reponse numero choix
    while read -r prise; do
        prises+=("$prise")
    done <<< "$(awk '!vu[$1]++ { print $1 }' <<< "$CANDIDATS")"
    echo "Prises réseau de cette machine :"
    for numero in "${!prises[@]}"; do
        echo "  $((numero + 1))) ${prises[$numero]} : $(sous_reseaux_de "${prises[$numero]}" | paste -sd, -)"
    done
    while true; do
        if ! read -r -p "Quelle(s) prise(s) relient les caméras ? Numéro(s) séparé(s) par des espaces : " reponse; then
            echo
            echo "[ERREUR] Aucune réponse : relance le script pour choisir la prise des caméras." >&2
            exit 1
        fi
        choix=""
        for numero in ${reponse//,/ }; do
            case "$numero" in
                *[!0-9]*) choix=""; break ;;
            esac
            if [ "$numero" -lt 1 ] || [ "$numero" -gt "${#prises[@]}" ]; then
                choix=""
                break
            fi
            case ",$choix," in
                *",${prises[$((numero - 1))]},"*) ;;
                *) choix="${choix:+$choix,}${prises[$((numero - 1))]}" ;;
            esac
        done
        if [ -n "$choix" ]; then
            RETENUES="$choix"
            return
        fi
        echo "Réponse invalide : numéro(s) entre 1 et ${#prises[@]}."
    done
}

if [ ! -f "$FICHIER_ENV" ]; then
    echo "[ERREUR] $FICHIER_ENV introuvable : copie .env.example en .env, puis relance." >&2
    exit 1
fi

CANDIDATS="$(candidats)"
RETENUES="$(valeur_env "$CLE_INTERFACES")"

if [ -z "$RETENUES" ]; then
    nombre="$(awk '!vu[$1]++' <<< "$CANDIDATS" | grep -c .)"
    if [ "$nombre" -eq 0 ]; then
        echo "[AVERTISSEMENT] Aucune prise réseau avec une adresse privée : Détection non configurée."
        ecrire_env "$CLE_SOUS_RESEAUX" ""
        exit 0
    elif [ "$nombre" -eq 1 ]; then
        RETENUES="$(awk '{ print $1; exit }' <<< "$CANDIDATS")"
    elif [ -t 0 ]; then
        choisir_prises
    else
        echo "[AVERTISSEMENT] Plusieurs prises réseau et aucune retenue pour les caméras : Détection non configurée."
        echo "                Lance une fois scripts/cameras/configurer-detection.sh dans un terminal pour choisir."
        ecrire_env "$CLE_SOUS_RESEAUX" ""
        exit 0
    fi
    ecrire_env "$CLE_INTERFACES" "$RETENUES"
fi

sous_reseaux=""
total=0
for prise in ${RETENUES//,/ }; do
    trouves="$(sous_reseaux_de "$prise")"
    if [ -z "$trouves" ]; then
        echo "[AVERTISSEMENT] Prise $prise : pas d'adresse IPv4 privée (câble débranché, pas de DHCP ?)."
        continue
    fi
    for reseau in $trouves; do
        case ",$sous_reseaux," in
            *",$reseau,"*) continue ;;
        esac
        sous_reseaux="${sous_reseaux:+$sous_reseaux,}$reseau"
        total=$((total + (1 << (32 - ${reseau#*/}))))
    done
done

if [ "$total" -gt "$PLAFOND" ]; then
    echo "[ERREUR] $sous_reseaux : $total adresses, plus que le plafond de $PLAFOND de la Détection." >&2
    echo "         Une Détection sur une plage aussi grande serait interminable : Détection non configurée." >&2
    echo "         Donne aux caméras un sous-réseau plus petit (ex. /24), ou écris $CLE_SOUS_RESEAUX à la main dans .env." >&2
    ecrire_env "$CLE_SOUS_RESEAUX" ""
    exit 1
fi

ecrire_env "$CLE_SOUS_RESEAUX" "$sous_reseaux"
if [ -n "$sous_reseaux" ]; then
    echo "Détection des Caméras : prise(s) $RETENUES, sous-réseau(x) $sous_reseaux."
else
    echo "[AVERTISSEMENT] Détection non configurée : aucune prise retenue n'a d'adresse."
fi
