#!/bin/sh
# Diffuse /media/video.mp4 en boucle sur le chemin de la Caméra simulée (runOnInit de camera-simulee.yml).
# Sans FICHIER_DATE : copie de flux, sans réencodage. Avec : la date et l'heure de la caméra, écrites dans ce
# fichier par son interface ONVIF (simulation/onvif/README.md), incrustées en bas à gauche, relues à chaque image ;
# la vidéo est alors réencodée à la volée, dans son codec (H.264 ou H.265), keyframe toutes les 2 s, sans B-frames.
set -eu

SORTIE="rtsp://localhost:$RTSP_PORT/$MTX_PATH"
LECTURE="-hide_banner -loglevel error -re -stream_loop -1 -i /media/video.mp4"

if [ -z "${FICHIER_DATE:-}" ]; then
    # shellcheck disable=SC2086
    exec ffmpeg $LECTURE -c copy -f rtsp "$SORTIE"
fi

# drawtext refuse un fichier absent : l'interface ONVIF l'écrit dès son démarrage.
while [ ! -s "$FICHIER_DATE" ]; do
    sleep 0.2
done

INCRUSTATION="drawtext=fontfile=/usr/share/fonts/dejavu/DejaVuSansMono.ttf:textfile=$FICHIER_DATE:reload=1"
INCRUSTATION="$INCRUSTATION:x=16:y=h-th-16:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=6"
if [ "$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 /media/video.mp4)" = hevc ]; then
    CODAGE="-c:v libx265 -tag:v hvc1 -x265-params bframes=0:keyint=30:min-keyint=30:scenecut=0:log-level=error"
else
    CODAGE="-c:v libx264 -bf 0 -g 30 -keyint_min 30 -sc_threshold 0"
fi
# shellcheck disable=SC2086
exec ffmpeg $LECTURE -vf "$INCRUSTATION" $CODAGE -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
    -f rtsp "$SORTIE"
