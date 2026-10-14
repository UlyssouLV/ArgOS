#!/bin/sh
# Certificats du Site (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md), lancé à chaque
# `docker compose up` avant `web` :
# - l'Autorité du Site (10 ans) est créée si elle manque, jamais remplacée sinon : les postes qui l'ont
#   installée la gardent ;
# - le certificat serveur (397 jours, signé par l'Autorité) nomme localhost, 127.0.0.1 et chaque entrée
#   de MTX_WEBRTCADDITIONALHOSTS (IP du Site sur le réseau local) ; il est régénéré, avec la même Autorité,
#   s'il manque, si ses noms diffèrent de ceux attendus (nouvelle IP du Site) ou s'il lui reste moins de
#   30 jours, et gardé sinon ;
# - web ne reçoit que le certificat serveur, sa clé et la partie publique de l'Autorité (argos-ca.crt) ;
#   api, que le certificat serveur (public/serveur.crt), pour reconnaître l'hôte du Site (argos_api/soi.py).
# Avec ARGOS_CERTIFICAT_DOSSIER (certificat de l'Administrateur : nom de domaine, VPN), certificat.crt et cle.key
# de ce dossier sont servis tels quels : ni Autorité du Site, ni génération, ni renouvellement, ni argos-ca.crt.
set -eu

AUTORITE=/autorite
SERVEUR=/certificats-serveur
# Dossier ARGOS_CERTIFICAT_DOSSIER, monté en lecture seule par compose.yaml.
FOURNI=/certificat-fourni
# Le certificat serveur est régénéré quand il lui reste moins que ce délai (30 jours).
RENOUVELER_AVANT_S=2592000

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

# Noms d'un texte `openssl … -text` (certificat ou demande), un par ligne et triés, écrits par openssl
# lui-même : une IPv6 déclarée en abrégé se compare à celle du certificat.
noms_lus() {
  awk '/X509v3 Subject Alternative Name/ { getline; print; exit }' | tr ',' '\n' | sed 's/^ *//' | sort -u
}

noms_du_certificat() {
  openssl x509 -noout -text -in "$SERVEUR/serveur.crt" | noms_lus
}

noms_attendus() {
  openssl req -new -key "$SERVEUR/serveur.key" -subj "/CN=ArgOS" -addext "subjectAltName=$(noms_du_serveur)" \
    | openssl req -noout -text | noms_lus
}

# Pourquoi régénérer le certificat serveur ; rien s'il est à garder.
raison_de_regenerer() {
  if [ ! -s "$SERVEUR/serveur.crt" ] || [ ! -s "$SERVEUR/serveur.key" ]; then
    echo "absent"
  elif ! openssl verify -CAfile "$AUTORITE/autorite.crt" "$SERVEUR/serveur.crt" >/dev/null 2>&1; then
    echo "pas signé par l'Autorité du Site"
  elif [ "$(noms_du_certificat)" != "$(noms_attendus)" ]; then
    echo "noms changés"
  elif ! openssl x509 -noout -checkend "$RENOUVELER_AVANT_S" -in "$SERVEUR/serveur.crt" >/dev/null; then
    echo "moins de 30 jours de validité"
  fi
}

# Installe pour web un certificat serveur et sa clé (`<source> <clé source>`), et le certificat seul pour api.
installer_serveur() {
  mkdir -p "$SERVEUR/public"
  cp "$1" "$SERVEUR/serveur.crt.tmp"
  cp "$1" "$SERVEUR/public/serveur.crt.tmp"
  cp "$2" "$SERVEUR/serveur.key.tmp"
  chmod 400 "$SERVEUR/serveur.key.tmp"
  chmod 644 "$SERVEUR/serveur.crt.tmp" "$SERVEUR/public/serveur.crt.tmp"
  mv "$SERVEUR/serveur.key.tmp" "$SERVEUR/serveur.key"
  mv "$SERVEUR/serveur.crt.tmp" "$SERVEUR/serveur.crt"
  mv "$SERVEUR/public/serveur.crt.tmp" "$SERVEUR/public/serveur.crt"
}

# Lancé en utilisateur 101 (Dockerfile) : un volume créé par une version lancée en root lui est fermé.
for volume in "$AUTORITE" "$SERVEUR"; do
  if [ ! -w "$volume" ]; then
    echo "$volume : non modifiable par l'utilisateur $(id -u) (volume créé par une version antérieure d'ArgOS)." >&2
    echo "Les lui donner, Autorité gardée, puis relancer la stack :" >&2
    echo "  docker compose run --rm --no-deps --user 0 --entrypoint chown certificats -R 101:101 $AUTORITE $SERVEUR" >&2
    exit 1
  fi
done

if [ -n "${ARGOS_CERTIFICAT_DOSSIER:-}" ]; then
  for fichier in certificat.crt cle.key; do
    if [ ! -s "$FOURNI/$fichier" ] || [ ! -r "$FOURNI/$fichier" ]; then
      echo "ARGOS_CERTIFICAT_DOSSIER ($ARGOS_CERTIFICAT_DOSSIER) : $fichier manquant, vide ou illisible par l'utilisateur $(id -u)." >&2
      echo "Y déposer certificat.crt (certificat du Site, chaîne comprise) et cle.key (sa clé), ou vider la variable dans .env." >&2
      exit 1
    fi
  done
  installer_serveur "$FOURNI/certificat.crt" "$FOURNI/cle.key"
  # Pas d'Autorité du Site à installer sur les postes : /argos-ca.crt répond 404.
  rm -f "$SERVEUR/argos-ca.crt"
  echo "Certificat fourni par l'Administrateur ($ARGOS_CERTIFICAT_DOSSIER) : servi tel quel, sans Autorité du Site ni renouvellement."
  exit 0
fi

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

raison=$(raison_de_regenerer)
if [ -n "$raison" ]; then
  san=$(noms_du_serveur)
  echo "Certificat serveur ($raison) : création (397 jours) pour $san."
  umask 077
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$SERVEUR/nouveau.key"
  openssl req -x509 -new -sha256 -days 397 \
    -key "$SERVEUR/nouveau.key" \
    -CA "$AUTORITE/autorite.crt" -CAkey "$AUTORITE/autorite.key" \
    -subj "/O=ArgOS/CN=ArgOS" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "keyUsage=critical,digitalSignature" \
    -addext "extendedKeyUsage=serverAuth" \
    -addext "subjectAltName=$san" \
    -out "$SERVEUR/nouveau.crt"
  umask 022
  installer_serveur "$SERVEUR/nouveau.crt" "$SERVEUR/nouveau.key"
  rm "$SERVEUR/nouveau.crt" "$SERVEUR/nouveau.key"
else
  echo "Certificat serveur gardé : mêmes noms, plus de 30 jours de validité."
  # Gardé, recopié tel quel : le dossier public d'api manque dans un volume créé avant lui.
  installer_serveur "$SERVEUR/serveur.crt" "$SERVEUR/serveur.key"
fi

cp "$AUTORITE/autorite.crt" "$SERVEUR/argos-ca.crt.tmp"
chmod 644 "$SERVEUR/argos-ca.crt.tmp"
mv "$SERVEUR/argos-ca.crt.tmp" "$SERVEUR/argos-ca.crt"

empreinte=$(openssl x509 -noout -fingerprint -sha256 -in "$AUTORITE/autorite.crt" | cut -d= -f2)
echo "Empreinte SHA-256 de l'Autorité du Site : $empreinte"
echo "À comparer avec celle du fichier téléchargé en HTTP sur chaque poste (<IP du Site>/argos-ca.crt)."
