#!/bin/sh
# Certificats du Site (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md), lancé à chaque
# `docker compose up` avant `web` :
# - l'Autorité du Site (10 ans) est créée si elle manque, jamais remplacée sinon : les postes qui l'ont
#   installée la gardent ;
# - le certificat serveur (397 jours, signé par l'Autorité) nomme localhost, 127.0.0.1 et chaque entrée
#   de MTX_WEBRTCADDITIONALHOSTS (IP du Site sur le réseau local) ;
# - web ne reçoit que le certificat serveur, sa clé et la partie publique de l'Autorité (argos-ca.crt).
set -eu

AUTORITE=/autorite
SERVEUR=/certificats-serveur
# Utilisateur de nginx dans l'image de web (nginx-unprivileged) : seul lecteur de la clé du serveur.
UTILISATEUR_WEB=101

# Noms du certificat serveur, sans doublon : IP (v4 ou v6) en IP:, le reste en DNS:.
noms_du_serveur() {
  vus=""
  san=""
  for nom in localhost 127.0.0.1 $(echo "${MTX_WEBRTCADDITIONALHOSTS:-}" | tr ',' ' '); do
    case " $vus " in *" $nom "*) continue ;; esac
    vus="$vus $nom"
    if echo "$nom" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$|:'; then
      san="$san,IP:$nom"
    else
      san="$san,DNS:$nom"
    fi
  done
  echo "${san#,}"
}

if [ ! -s "$AUTORITE/autorite.key" ] || [ ! -s "$AUTORITE/autorite.crt" ]; then
  echo "Autorité du Site absente : création (10 ans)."
  umask 077
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$AUTORITE/autorite.key.tmp"
  openssl req -x509 -new -utf8 -sha256 -days 3650 \
    -key "$AUTORITE/autorite.key.tmp" \
    -subj "/O=ArgOS/CN=Autorité du Site ArgOS" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" \
    -out "$AUTORITE/autorite.crt.tmp"
  mv "$AUTORITE/autorite.key.tmp" "$AUTORITE/autorite.key"
  mv "$AUTORITE/autorite.crt.tmp" "$AUTORITE/autorite.crt"
  umask 022
fi

# Absent, ou signé par une Autorité perdue depuis : un nouveau certificat serveur.
if [ ! -s "$SERVEUR/serveur.crt" ] || [ ! -s "$SERVEUR/serveur.key" ] \
  || ! openssl verify -CAfile "$AUTORITE/autorite.crt" "$SERVEUR/serveur.crt" >/dev/null 2>&1; then
  san=$(noms_du_serveur)
  echo "Certificat serveur : création (397 jours) pour $san."
  umask 077
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$SERVEUR/serveur.key.tmp"
  openssl req -x509 -new -sha256 -days 397 \
    -key "$SERVEUR/serveur.key.tmp" \
    -CA "$AUTORITE/autorite.crt" -CAkey "$AUTORITE/autorite.key" \
    -subj "/O=ArgOS/CN=ArgOS" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "keyUsage=critical,digitalSignature" \
    -addext "extendedKeyUsage=serverAuth" \
    -addext "subjectAltName=$san" \
    -out "$SERVEUR/serveur.crt.tmp"
  umask 022
  chown "$UTILISATEUR_WEB:$UTILISATEUR_WEB" "$SERVEUR/serveur.key.tmp"
  chmod 400 "$SERVEUR/serveur.key.tmp"
  chmod 644 "$SERVEUR/serveur.crt.tmp"
  mv "$SERVEUR/serveur.key.tmp" "$SERVEUR/serveur.key"
  mv "$SERVEUR/serveur.crt.tmp" "$SERVEUR/serveur.crt"
fi

cp "$AUTORITE/autorite.crt" "$SERVEUR/argos-ca.crt.tmp"
chmod 644 "$SERVEUR/argos-ca.crt.tmp"
mv "$SERVEUR/argos-ca.crt.tmp" "$SERVEUR/argos-ca.crt"

empreinte=$(openssl x509 -noout -fingerprint -sha256 -in "$AUTORITE/autorite.crt" | cut -d= -f2)
echo "Empreinte SHA-256 de l'Autorité du Site : $empreinte"
echo "À comparer avec celle du fichier téléchargé sur chaque poste (http://<IP du Site>/argos-ca.crt)."
