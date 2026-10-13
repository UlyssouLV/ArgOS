# Caméras simulées

Fichiers de **dev**, utilisés seulement par `compose.simulation.yaml` (jamais par la stack de prod). Ce ne sont pas des enregistrements produit : à remplacer plus tard par de vraies caméras IP.

Chaque Caméra simulée est un conteneur à part, comme une vraie caméra IP : un MediaMTX ([`camera-simulee.yml`](camera-simulee.yml)) où ffmpeg diffuse sa vidéo en boucle, sans réencodage, en RTSP sur le port **554**, sur un seul chemin, celui d’une vraie caméra (variable `CHEMIN_FLUX` dans `compose.simulation.yaml`, qui remplit le gabarit `camera-simulee.yml`). Les Caméras simulées vivent sur le réseau Compose `cameras-simulees` (`172.30.0.0/24`), chacune à une IP et une MAC **fixes** (comme le bail et l’étiquette d’une vraie caméra ; les autres conteneurs y prennent leur IP dans `172.30.0.128/26`), et ne sont **pas publiées** sur la machine hôte : on les déclare comme Caméras (Administration), puis on les regarde dans le Live.

| Caméra simulée     | IP / MAC | URL RTSP (vue de `api` et du pont) | Style du chemin | Vidéo      | Origine (source déposée)                                       |
|--------------------|----------|------------------------------------|-----------------|------------|----------------------------------------------------------------|
| `camera-simulee-1` | `172.30.0.11` / `02:a6:05:00:00:01` | `rtsp://camera-simulee-1/Streaming/Channels/101` | Hikvision | `cam1.mp4` | Security Camera (CCTV) Style Video in After Effects            |
| `camera-simulee-2` | `172.30.0.12` / `02:a6:05:00:00:02` | `rtsp://admin:argos-simulee@camera-simulee-2/cam/realmonitor?channel=1&subtype=0` | Dahua | `cam2.mp4` | 8MP 4K Dahua CCTV System Sample Video — Night Time             |
| `camera-simulee-3` | `172.30.0.13` / `02:a6:05:00:00:03` | `rtsp://camera-simulee-3/flux` | exotique (aucun chemin courant) | `cam3.mp4` | Example of Hi-Definition Video Surveillance of a Factory Floor |
| `camera-simulee-4` | `172.30.0.14` / `02:a6:05:00:00:04` | `rtsp://camera-simulee-4/Streaming/Channels/101` | Hikvision, en **H.265** | `cam4.mp4` | `cam1.mp4` réencodée en H.265 (voir plus bas) |

## Identifiants de `camera-simulee-2`

`camera-simulee-2` exige, comme beaucoup de vraies caméras, un identifiant et un mot de passe pour lire le Flux :

- identifiant : `admin`
- mot de passe : `argos-simulee`

Identifiants **de dev**, publics dans le dépôt (définis dans `compose.simulation.yaml`). Sans eux, ou avec un mauvais mot de passe, la Caméra répond `401 Unauthorized`, et une Caméra déclarée sans eux reste `offline`. Une requête `OPTIONS` sans identifiants reçoit quand même une réponse RTSP.

## Format attendu

- H.264 (`cam4.mp4` : H.265, tag `hvc1`), 1280×720, 15 i/s, **sans audio**, sans B-frames
- Keyframe ~2 s, ≤ 50 Mo
- Diffusion en **copie de flux** (`-c copy`), sans réencodage à la volée

La conversion est faite **une fois**, avant commit (ffmpeg en conteneur, seul prérequis : Docker). État : `cam1.mp4`, `cam2.mp4` et `cam3.mp4` convertis ; `cam4.mp4` encodée depuis `cam1.mp4`.

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

## `cam4.mp4` : `cam1.mp4` en H.265 (référence)

Les mêmes images que `camera-simulee-1`, réencodées une fois en HEVC : 1280×720, 15 i/s, GOP 30 (keyframe 2 s), sans B-frames, sans audio. Le tag `hvc1` (plutôt que `hev1`) est celui que Safari et les lecteurs MSE attendent en MP4.

```bash
# depuis media/simulated/
docker run --rm -v "$PWD":/v --entrypoint ffmpeg bluenviron/mediamtx:1.21.1-ffmpeg \
  -y -i /v/cam1.mp4 \
  -map 0:v:0 -an -c:v libx265 -pix_fmt yuv420p -r 15 -g 30 -keyint_min 30 -sc_threshold 0 -bf 0 \
  -x265-params "bframes=0:keyint=30:min-keyint=30:scenecut=0:log-level=error" -tag:v hvc1 \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -preset medium -crf 28 -movflags +faststart \
  /v/cam4.converted.mp4
mv cam4.converted.mp4 cam4.mp4
```

Image `bluenviron/mediamtx:1.21.1-ffmpeg` (celle des Caméras simulées) : le libx265 de `linuxserver/ffmpeg:version-7.1-cli` s’arrête en erreur de segmentation, sur arm64 comme sur amd64.

Vérifier le résultat (attendu : `codec_name=hevc`, `codec_tag_string=hvc1`, `1280×720`, `15/1`, `has_b_frames=0`) :

```bash
docker run --rm -v "$PWD":/v --entrypoint ffprobe bluenviron/mediamtx:1.21.1-ffmpeg \
  -v error -show_entries stream=codec_name,codec_tag_string,codec_type,width,height,r_frame_rate,has_b_frames -of compact /v/cam4.mp4
```
