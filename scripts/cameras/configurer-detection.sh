#!/usr/bin/env bash
# Configure la Détection des Caméras, sur la machine hôte (Linux : ip, macOS : ifconfig).
# Premier lancement en terminal : demande la ou les prises qui relient les caméras (aucune question
# s'il n'y en a qu'une) et les retient dans .env (ARGOS_DETECTION_CAMERAS_INTERFACES).
# Chaque lancement : recalcule le(s) sous-réseau(x) de ces prises et les écrit dans .env
# (ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX). Sans terminal (démarrage automatique) : aucune question.
# Linux seulement, réseau des caméras (macvlan, ADR 0003) sur la première prise retenue : propose une fois
# en terminal une IP libre pour ArgOS (vérifiée par ARP), la retient (ARGOS_RESEAU_CAMERAS_IP), et ajoute
# compose.reseau-cameras.yaml à COMPOSE_FILE ; avertit et le retire si l'IP retenue ne convient plus.
# Sous macOS (Docker Desktop, pas de macvlan) : rien de tout cela.
# Voir ADR 0002 et 0003. Fichier .env : ARGOS_FICHIER_ENV, sinon celui de la racine du dépôt.
set -u

RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
FICHIER_ENV="${ARGOS_FICHIER_ENV:-$RACINE/.env}"
CLE_INTERFACES=ARGOS_DETECTION_CAMERAS_INTERFACES
CLE_SOUS_RESEAUX=ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX
# Même plafond que l'API : au-delà, une Détection ne tiendrait pas en une dizaine de secondes.
PLAFOND=1024
CLE_IP_CAMERAS=ARGOS_RESEAU_CAMERAS_IP
CLE_PRISE_CAMERAS=ARGOS_RESEAU_CAMERAS_PRISE
CLE_SOUS_RESEAU_CAMERAS=ARGOS_RESEAU_CAMERAS_SOUS_RESEAU
FICHIER_COMPOSE_CAMERAS=compose.reseau-cameras.yaml
# Adresses essayées au plus, depuis le haut du sous-réseau, pour proposer une IP libre à ArgOS.
ESSAIS_IP=16

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

en_entier() {
    local a b c d
    IFS=. read -r a b c d <<< "$1"
    echo $(((a << 24) | (b << 16) | (c << 8) | d))
}

en_adresse() {
    echo "$(($1 >> 24 & 255)).$(($1 >> 16 & 255)).$(($1 >> 8 & 255)).$(($1 & 255))"
}

sous_reseau() {
    local adresse="$1" prefixe="$2" masque
    masque=$(((0xffffffff << (32 - prefixe)) & 0xffffffff))
    echo "$(en_adresse $(($(en_entier "$adresse") & masque)))/$prefixe"
}

# Vrai si $1 est une adresse IPv4 d'hôte du sous-réseau $2 (ni l'adresse du réseau, ni la diffusion).
hote_du_sous_reseau() {
    local adresse="$1" reseau="$2" octet debut taille entier
    [[ "$adresse" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
    for octet in ${adresse//./ }; do
        [ "$((10#$octet))" -le 255 ] || return 1
    done
    debut="$(en_entier "${reseau%/*}")"
    taille=$((1 << (32 - ${reseau#*/})))
    entier="$(en_entier "$adresse")"
    [ "$entier" -gt "$debut" ] && [ "$entier" -lt $((debut + taille - 1)) ]
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

# Vrai si un appareil répond en ARP à l'adresse $1 sur la prise $2 : le ping (même sans réponse) fait
# demander la MAC par la machine, qui l'inscrit dans sa table de voisinage.
repond_en_arp() {
    ping -c 1 -W 1 -I "$2" "$1" > /dev/null 2>&1
    ip neigh show to "$1" dev "$2" | grep -q lladdr
}

# Première adresse libre du sous-réseau $2 de la prise $1, depuis le haut (loin des baux DHCP courants).
proposer_ip() {
    local prise="$1" reseau="$2" entier essai adresse
    entier=$(($(en_entier "${reseau%/*}") + (1 << (32 - ${reseau#*/})) - 2))
    for ((essai = 0; essai < ESSAIS_IP; essai++)); do
        adresse="$(en_adresse $((entier - essai)))"
        hote_du_sous_reseau "$adresse" "$reseau" || return 1
        if ! grep -qxF "$adresse" <<< "$ADRESSES_MACHINE" && ! repond_en_arp "$adresse" "$prise"; then
            echo "$adresse"
            return
        fi
    done
    return 1
}

demander_ip() {
    local prise="$1" reseau="$2" proposee="$3" reponse
    echo "ArgOS rejoint le réseau des caméras ($prise, $reseau) à une IP fixe pour y lire leurs MAC."
    echo "Choisis-la hors de la plage DHCP de ta box ou de ton routeur."
    while true; do
        if ! read -r -p "IP d'ArgOS sur le réseau des caméras${proposee:+ [$proposee]} : " reponse; then
            echo
            echo "[AVERTISSEMENT] Aucune réponse : réseau des caméras non activé (pas de MAC pour les vraies caméras)."
            return 1
        fi
        reponse="${reponse//[[:space:]]/}"
        reponse="${reponse:-$proposee}"
        if ! hote_du_sous_reseau "$reponse" "$reseau"; then
            echo "Réponse invalide : une adresse de $reseau, ni la première ni la dernière."
        elif [ "$reponse" != "$proposee" ] && repond_en_arp "$reponse" "$prise"; then
            echo "$reponse répond déjà en ARP : un autre appareil l'occupe, choisis-en une autre."
        else
            IP_CAMERAS="$reponse"
            return
        fi
    done
}

valeur_compose_file() {
    local actuel
    actuel="$(valeur_env COMPOSE_FILE)"
    echo "${actuel:-compose.yaml}"
}

activer_reseau_cameras() {
    local actuel
    actuel="$(valeur_compose_file)"
    case ":$actuel:" in
        *":$FICHIER_COMPOSE_CAMERAS:"*) ;;
        *) ecrire_env COMPOSE_FILE "$actuel:$FICHIER_COMPOSE_CAMERAS" ;;
    esac
}

desactiver_reseau_cameras() {
    local actuel
    actuel="$(valeur_env COMPOSE_FILE)"
    case ":$actuel:" in
        *":$FICHIER_COMPOSE_CAMERAS:"*)
            ecrire_env COMPOSE_FILE "$(tr ':' '\n' <<< "$actuel" | grep -vxF "$FICHIER_COMPOSE_CAMERAS" | paste -sd: -)"
            ;;
    esac
}

# Réseau des caméras (Linux) : macvlan sur la première prise retenue qui a une adresse.
configurer_reseau_cameras() {
    local prise premiere="" reseau="" trouve ip_retenue
    for prise in ${RETENUES//,/ }; do
        trouve="$(sous_reseaux_de "$prise" | head -n 1)"
        [ -n "$trouve" ] || continue
        if [ -z "$premiere" ]; then
            premiere="$prise"
            reseau="$trouve"
        else
            echo "[AVERTISSEMENT] Prise $prise : réseau des caméras sur $premiere seulement, ses caméras restent sans MAC."
        fi
    done
    if [ -z "$premiere" ]; then
        desactiver_reseau_cameras
        return
    fi
    ecrire_env "$CLE_PRISE_CAMERAS" "$premiere"
    ecrire_env "$CLE_SOUS_RESEAU_CAMERAS" "$reseau"
    ADRESSES_MACHINE="$(adresses | awk '{ print $2 }')"

    ip_retenue="$(valeur_env "$CLE_IP_CAMERAS")"
    if [ -n "$ip_retenue" ] && ! hote_du_sous_reseau "$ip_retenue" "$reseau"; then
        echo "[AVERTISSEMENT] IP d'ArgOS sur le réseau des caméras $ip_retenue : hors du sous-réseau $reseau de la prise $premiere."
        if [ ! -t 0 ]; then
            echo "                Réseau des caméras désactivé : relance le script dans un terminal pour en choisir une autre."
            desactiver_reseau_cameras
            return
        fi
        ip_retenue=""
    elif [ -n "$ip_retenue" ] && repond_en_arp "$ip_retenue" "$premiere"; then
        echo "[AVERTISSEMENT] IP d'ArgOS sur le réseau des caméras $ip_retenue : répond déjà en ARP, un autre appareil l'occupe."
        echo "                Réseau des caméras désactivé : retire $CLE_IP_CAMERAS de .env, puis relance le script dans un terminal."
        desactiver_reseau_cameras
        return
    fi
    if [ -z "$ip_retenue" ]; then
        if [ ! -t 0 ]; then
            echo "[AVERTISSEMENT] Réseau des caméras non activé (pas de MAC pour les vraies caméras) : aucune IP d'ArgOS retenue."
            echo "                Lance une fois scripts/cameras/configurer-detection.sh dans un terminal pour la choisir."
            desactiver_reseau_cameras
            return
        fi
        if ! demander_ip "$premiere" "$reseau" "$(proposer_ip "$premiere" "$reseau")"; then
            desactiver_reseau_cameras
            return
        fi
        ip_retenue="$IP_CAMERAS"
        ecrire_env "$CLE_IP_CAMERAS" "$ip_retenue"
    fi
    activer_reseau_cameras
    echo "Réseau des caméras : ArgOS à $ip_retenue sur la prise $premiere ($reseau)."
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

if [ "$(uname -s)" = Linux ]; then
    configurer_reseau_cameras
fi
