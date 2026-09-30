# Vidéos des Caméras simulées

Fichiers de **dev** pour MediaMTX (`cam1`, `cam2`, `cam3`). Ce ne sont pas des enregistrements produit : à remplacer plus tard par de vraies caméras IP.

Chaque `camN.mp4` est diffusé en boucle par MediaMTX sur `rtsp://<hôte>:8554/camN` (config : [`../mediamtx.yml`](../mediamtx.yml)). Le nom du fichier donne le chemin.

## Fichiers

| Fichier     | Rôle                          | Origine (source déposée)                                      |
|-------------|-------------------------------|----------------------------------------------------------------|
| `cam1.mp4`  | Caméra simulée `cam1`         | Security Camera (CCTV) Style Video in After Effects            |
| `cam2.mp4`  | Caméra simulée `cam2`         | 8MP 4K Dahua CCTV System Sample Video — Night Time             |
| `cam3.mp4`  | Caméra simulée `cam3`         | Example of Hi-Definition Video Surveillance of a Factory Floor |

## Format attendu

- H.264, 1280×720, 15 i/s, **sans audio**, sans B-frames
- Keyframe ~2 s, ≤ 50 Mo
- Diffusion MediaMTX en **copie de flux** (`-c copy`), sans réencodage à la volée

La conversion est faite **une fois**, avant commit (ffmpeg en conteneur, seul prérequis : Docker). État : `cam1.mp4`, `cam2.mp4` et `cam3.mp4` convertis.

## Conversion (référence)

```bash
# depuis media/simulated/
docker run --rm -v "$PWD":/v linuxserver/ffmpeg:version-7.1-cli \
  -y -i /v/camN.mp4 \
  -map 0:v:0 -an -c:v libx264 -pix_fmt yuv420p -r 15 -g 30 -keyint_min 30 -sc_threshold 0 -bf 0 \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -preset medium -crf 23 -movflags +faststart \
  /v/camN.converted.mp4
mv camN.converted.mp4 camN.mp4
```

`-map 0:v:0` garde la première piste vidéo : certaines sources embarquent une image de couverture (MJPEG) que ffmpeg choisirait sinon. `-bf 0` évite les B-frames, que WebRTC ne lit pas.

Vérifier le résultat :

```bash
docker run --rm -v "$PWD":/v --entrypoint ffprobe linuxserver/ffmpeg:version-7.1-cli \
  -v error -show_entries stream=codec_name,codec_type,width,height,r_frame_rate -of compact /v/camN.mp4
```
