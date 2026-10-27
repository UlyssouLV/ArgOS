#!/bin/sh
# Une piste de la Caméra simulée à l'audio en avance (camera-simulee-audio-en-avance.yml), envoyée en RTP sur
# 127.0.0.1:5004, où MediaMTX réunit les deux pistes sur le chemin de la caméra. Un ffmpeg par piste : dans un seul
# ffmpeg, l'ordonnanceur freine la piste en avance pour la garder alignée sur l'autre, et l'écart ne se crée pas (#172).
# `video` : /media/video.mp4 en boucle (H.265), l'heure locale incrustée en bas à gauche, réencodée à la volée,
# keyframe toutes les 2 s, sans B-frames, paramètres VPS/SPS/PPS répétés dans le flux (le SDP ne les porte pas).
# `audio` : un souffle G.711 µ-law 8 kHz mono, dont l'horodatage court deux fois plus vite que l'heure réelle pendant
# ses AVANCE_AUDIO_S premières secondes : il finit en avance d'autant sur la vidéo, comme Cam 01.
set -eu

SORTIE="rtp://127.0.0.1:5004?pkt_size=1400"

case "$1" in
video)
    INCRUSTATION="drawtext=fontfile=/usr/share/fonts/dejavu/DejaVuSansMono.ttf:text='%{localtime\:%F %T}'"
    INCRUSTATION="$INCRUSTATION:x=16:y=h-th-16:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=6"
    exec ffmpeg -hide_banner -loglevel error -re -stream_loop -1 -i /media/video.mp4 -map 0:v -vf "$INCRUSTATION" \
        -c:v libx265 -x265-params bframes=0:keyint=30:min-keyint=30:scenecut=0:repeat-headers=1:log-level=error \
        -preset ultrafast -tune zerolatency -pix_fmt yuv420p -payload_type 96 -sdp_file /dev/null -f rtp "$SORTIE"
    ;;
audio)
    exec ffmpeg -hide_banner -loglevel error -re -f lavfi -i anoisesrc=sample_rate=8000:amplitude=0.02 \
        -af "asetpts=PTS+min(T\,$AVANCE_AUDIO_S)/TB" -c:a pcm_mulaw -ac 1 \
        -payload_type 0 -sdp_file /dev/null -f rtp "$SORTIE"
    ;;
esac
