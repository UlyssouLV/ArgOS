#!/bin/sh
# Lance chrony d'après la source de l'heure, et le relance avec sa nouvelle configuration quand le réglage change.
# -x : chrony ne règle jamais l'horloge de l'hôte (pas de SYS_TIME) ; il sert l'heure estimée de sa source.
set -u

SOURCE_PAR_DEFAUT="${ARGOS_TEMPS_SOURCE:-pool.ntp.org}"
# Source choisie dans l'Heure du Site, écrite par api (volume partagé, lecture seule ici) : une ligne, le serveur
# NTP, vide pour l'horloge du serveur. Absent (api pas encore démarré) : la source par défaut.
REGLAGE=/reglage/source
CONFIGURATION=/etc/chrony/chrony.conf
DERIVE=/var/lib/argos-temps/drift
PIDFILE=/run/chronyd.pid
# Secondes entre deux lectures du réglage.
PERIODE_REGLAGE_S=2

source_voulue() {
    if [ -f "$REGLAGE" ]; then
        # Un nom ou une adresse, rien d'autre : le réglage ne peut pas injecter de directive chrony.
        head -n 1 "$REGLAGE" | tr -cd 'A-Za-z0-9.:-'
    else
        echo "$SOURCE_PAR_DEFAUT"
    fi
}

ecrire_configuration() {
    {
        if [ -n "$1" ]; then
            echo "pool $1 iburst"
        fi
        cat <<FIN
# Source injoignable, ou aucune : l'horloge du serveur, servie en strate 10.
local stratum 10
# Sert l'heure à qui la demande, sur UDP 123 seulement.
allow all
# Aucune commande chrony par le réseau : seulement par la socket locale du conteneur.
cmdport 0
driftfile $DERIVE
# Hors de /run/chrony, à l'utilisateur chrony : root l'écrit sans DAC_OVERRIDE.
pidfile $PIDFILE
FIN
    } > "$CONFIGURATION"
}

lancer_chronyd() {
    ecrire_configuration "$1"
    # Le pidfile d'un chronyd arrêté (ou d'avant un redémarrage du conteneur) l'empêcherait de démarrer.
    rm -f "$PIDFILE"
    # -u chrony : après avoir ouvert le port 123, chrony quitte root.
    chronyd -d -x -u chrony -f "$CONFIGURATION" &
    chronyd=$!
}

# Sans KILL, root ne peut pas signaler chronyd une fois devenu chrony : chrony s'arrête lui-même.
arreter_chronyd() {
    su -s /bin/sh chrony -c "kill $chronyd" 2>/dev/null
    wait "$chronyd"
}

# Un chronyd arrêté reste zombie jusqu'à `wait` : son dossier /proc existe encore.
chronyd_tourne() {
    [ -r "/proc/$chronyd/status" ] && ! grep -q '^State:[[:space:]]*Z' "/proc/$chronyd/status"
}

# Dérive initiale : fréquence nulle, incertitude 100 ppm. Sans elle, chrony part d'une incertitude
# énorme et sert l'horloge du serveur (strate 10) quelques minutes avant de suivre sa source.
# Conteneur redémarré : la dérive apprise par chrony est gardée.
if [ ! -f "$DERIVE" ]; then
    mkdir -p "$(dirname "$DERIVE")"
    echo "0.000 100.000" > "$DERIVE"
    chown -R chrony:chrony "$(dirname "$DERIVE")"
fi

trap 'arreter_chronyd; exit 0' TERM INT
suivie="$(source_voulue)"
lancer_chronyd "$suivie"
# Retirer sa source à chrony ne le fait pas revenir à l'horloge du serveur (il garde sa dernière estimation) :
# un réglage changé relance chronyd. Un chronyd arrêté seul est relancé aussi.
while :; do
    sleep "$PERIODE_REGLAGE_S" &
    wait $!
    voulue="$(source_voulue)"
    if [ "$voulue" != "$suivie" ] || ! chronyd_tourne; then
        arreter_chronyd
        suivie="$voulue"
        lancer_chronyd "$suivie"
    fi
done
