# Caméras simulées

Fichiers de **dev**, utilisés seulement par `compose.simulation.yaml` (jamais par la stack de prod). Ce ne sont pas des enregistrements produit : à remplacer plus tard par de vraies caméras IP.

Chaque Caméra simulée est un conteneur à part, comme une vraie caméra IP : un MediaMTX ([`camera-simulee.yml`](camera-simulee.yml)) où ffmpeg diffuse sa vidéo en boucle, sans réencodage, en RTSP sur le port **554**, sur un seul chemin, celui d’une vraie caméra (variable `CHEMIN_FLUX` dans `compose.simulation.yaml`, qui remplit le gabarit `camera-simulee.yml`). Les Caméras simulées vivent sur le réseau Compose `cameras-simulees` (`172.30.0.0/24`) et ne sont **pas publiées** sur la machine hôte : on les déclare comme Caméras (Administration), puis on les regarde dans le Live.

| Caméra simulée     | URL RTSP (vue de `api` et du pont) | Style du chemin | Vidéo      | Origine (source déposée)                                       |
|--------------------|------------------------------------|-----------------|------------|----------------------------------------------------------------|
| `camera-simulee-1` | `rtsp://camera-simulee-1/Streaming/Channels/101` | Hikvision | `cam1.mp4` | Security Camera (CCTV) Style Video in After Effects            |
| `camera-simulee-2` | `rtsp://admin:argos-simulee@camera-simulee-2/cam/realmonitor?channel=1&subtype=0` | Dahua | `cam2.mp4` | 8MP 4K Dahua CCTV System Sample Video — Night Time             |
| `camera-simulee-3` | `rtsp://camera-simulee-3/flux` | exotique (aucun chemin courant) | `cam3.mp4` | Example of Hi-Definition Video Surveillance of a Factory Floor |

## Identifiants de `camera-simulee-2`

`camera-simulee-2` exige, comme beaucoup de vraies caméras, un identifiant et un mot de passe pour lire le Flux :

- identifiant : `admin`
- mot de passe : `argos-simulee`

Identifiants **de dev**, publics dans le dépôt (définis dans `compose.simulation.yaml`). Sans eux, ou avec un mauvais mot de passe, la Caméra répond `401 Unauthorized`, et une Caméra déclarée sans eux reste `offline`. Une requête `OPTIONS` sans identifiants reçoit quand même une réponse RTSP.

## Format attendu

- H.264, 1280×720, 15 i/s, **sans audio**, sans B-frames
- Keyframe ~2 s, ≤ 50 Mo
- Diffusion en **copie de flux** (`-c copy`), sans réencodage à la volée

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
