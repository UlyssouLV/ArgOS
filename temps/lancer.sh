#!/bin/sh
# Écrit la configuration de chrony d'après la source de l'heure, puis le lance au premier plan.
# -x : chrony ne règle jamais l'horloge de l'hôte (pas de SYS_TIME) ; il sert l'heure estimée de sa source.
set -eu

SOURCE="${ARGOS_TEMPS_SOURCE:-pool.ntp.org}"
CONFIGURATION=/etc/chrony/chrony.conf
DERIVE=/var/lib/argos-temps/drift

# Dérive initiale : fréquence nulle, incertitude 100 ppm. Sans elle, chrony part d'une incertitude
# énorme et sert l'horloge du serveur (strate 10) quelques minutes avant de suivre sa source.
# Conteneur redémarré : la dérive apprise par chrony est gardée.
if [ ! -f "$DERIVE" ]; then
    mkdir -p "$(dirname "$DERIVE")"
    echo "0.000 100.000" > "$DERIVE"
    chown -R chrony:chrony "$(dirname "$DERIVE")"
fi

cat > "$CONFIGURATION" <<FIN
pool $SOURCE iburst
# Source injoignable : l'horloge du serveur, servie en strate 10.
local stratum 10
# Sert l'heure à qui la demande, sur UDP 123 seulement.
allow all
# Aucune commande chrony par le réseau : seulement par la socket locale du conteneur.
cmdport 0
driftfile $DERIVE
# Hors de /run/chrony, à l'utilisateur chrony : root l'écrit sans DAC_OVERRIDE.
pidfile /run/chronyd.pid
FIN

# Conteneur redémarré : le pidfile de l'ancien chronyd (pid 1 lui aussi) l'empêcherait de démarrer.
rm -f /run/chronyd.pid
# -u chrony : après avoir ouvert le port 123, chrony quitte root.
exec chronyd -d -x -u chrony -f "$CONFIGURATION"
