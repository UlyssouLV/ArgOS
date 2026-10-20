# Caméra simulée de dev (compose.simulation.yaml) : MediaMTX et ffmpeg, plus une police pour incruster la date
# des Caméras simulées ONVIF (diffuser.sh).
FROM bluenviron/mediamtx:1.21.1-ffmpeg

RUN apk add --no-cache font-dejavu
# Sans root : Docker laisse un utilisateur ouvrir le port 554 dans le réseau du conteneur ; la configuration
# remplie au lancement va dans /tmp (compose.simulation.yaml).
USER 65532
