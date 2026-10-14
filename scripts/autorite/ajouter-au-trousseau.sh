#!/usr/bin/env bash
# Autorité du Site sur le Mac hôte, une fois la stack démarrée (ADR 0005).
# Télécharge /argos-ca.crt sur le port HTTP local et affiche son empreinte SHA-256, à comparer avec celle
# des logs de certificats et des autres postes. Si elle n'est pas dans le trousseau de session, demande (o/n)
# avant de l'y ajouter comme racine de confiance (macOS demande alors le mot de passe) ; sinon, rien.
# Sans terminal : aucune question. Mode certificat fourni (/argos-ca.crt en 404) : rien à installer.
# Fichier .env : ARGOS_FICHIER_ENV, sinon celui de la racine du dépôt. N'échoue jamais : le lanceur continue.
set -u

RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
FICHIER_ENV="${ARGOS_FICHIER_ENV:-$RACINE/.env}"
TROUSSEAU="$HOME/Library/Keychains/login.keychain-db"

valeur_env() {
    sed -n "s/^$1=//p" "$FICHIER_ENV" | tail -n 1
}

port_http="$(valeur_env ARGOS_PORT_HTTP)"
port_http="${port_http:-80}"
case "$port_http" in
    80) url="http://localhost/argos-ca.crt" ;;
    *) url="http://localhost:$port_http/argos-ca.crt" ;;
esac

autorite="$(mktemp)"
trap 'rm -f "$autorite"' EXIT
if ! curl -fsS "$url" > "$autorite" 2>/dev/null; then
    echo "      Autorité du Site introuvable sur $url : rien à installer."
    exit 0
fi

empreinte="$(openssl x509 -in "$autorite" -noout -fingerprint -sha256 | sed 's/^.*=//')"
echo "      Empreinte SHA-256 de l'Autorité du Site :"
echo "      $empreinte"

# `security find-certificate -Z` donne l'empreinte en hexadécimal sans séparateur.
if security find-certificate -a -Z "$TROUSSEAU" 2>/dev/null | grep -qx "SHA-256 hash: ${empreinte//:/}"; then
    echo "      Déjà dans le trousseau de session : rien à faire."
    exit 0
fi
if [ ! -t 0 ]; then
    echo "      Absente du trousseau de session : relance dans un terminal pour l'ajouter."
    exit 0
fi
read -r -p "      Ajouter l'Autorité du Site au trousseau de session (macOS demandera le mot de passe) ? [o/n] " reponse
case "$reponse" in
    [oO]*) ;;
    *)
        echo "      Non ajoutée : le navigateur avertira à l'ouverture de l'UI."
        exit 0
        ;;
esac
if security add-trusted-cert -r trustRoot -k "$TROUSSEAU" "$autorite"; then
    echo "      Autorité du Site ajoutée au trousseau de session."
else
    echo "      Ajout refusé ou impossible : le navigateur avertira à l'ouverture de l'UI."
fi
