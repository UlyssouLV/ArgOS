#!/bin/sh
# Lancé avant nginx (/docker-entrypoint.d) : recharge nginx quand le service certificats remplace le certificat
# serveur (renouvellement à l'échéance, relance de la stack), sans redémarrer web. nginx ne lit son certificat
# qu'au chargement de sa configuration.
set -eu

CERTIFICATS=/etc/nginx/certificats

empreinte() {
  cat "$CERTIFICATS/serveur.crt" "$CERTIFICATS/serveur.key" 2>/dev/null | cksum
}

(
  servie=$(empreinte)
  while sleep 2; do
    nouvelle=$(empreinte)
    # Clé déjà remplacée mais pas encore le certificat : nginx -t échoue, on réessaie au tour suivant.
    if [ "$nouvelle" != "$servie" ] && nginx -t -q 2>/dev/null && nginx -s reload 2>/dev/null; then
      servie=$nouvelle
      echo "Certificat serveur remplacé : nginx rechargé."
    fi
  done
) &
