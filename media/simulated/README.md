# Caméras simulées

Fichiers de **dev**, utilisés seulement par `compose.simulation.yaml` (jamais par la stack de prod). Ce ne sont pas des enregistrements produit : à remplacer plus tard par de vraies caméras IP.

Chaque Caméra simulée est un conteneur à part, comme une vraie caméra IP : un MediaMTX ([`camera-simulee.yml`](camera-simulee.yml)) où ffmpeg ([`diffuser.sh`](diffuser.sh)) diffuse sa vidéo en boucle en RTSP sur le port **554**, sur un seul chemin, celui d’une vraie caméra (variable `CHEMIN_FLUX` dans `compose.simulation.yaml`, qui remplit le gabarit `camera-simulee.yml`). Les Caméras simulées vivent sur le réseau Compose `cameras-simulees` (`172.30.0.0/24`), chacune à une IP et une MAC **fixes** (comme le bail et l’étiquette d’une vraie caméra ; les autres conteneurs y prennent leur IP dans `172.30.0.128/26`), et ne sont **pas publiées** sur la machine hôte : on les déclare comme Caméras (Administration), puis on les regarde dans le Live.

| Caméra simulée     | IP / MAC | URL RTSP (vue de `api` et du pont) | Style du chemin | Vidéo      | Origine (source déposée)                                       |
|--------------------|----------|------------------------------------|-----------------|------------|----------------------------------------------------------------|
| `camera-simulee-1` | `172.30.0.11` / `02:a6:05:00:00:01` | `rtsp://camera-simulee-1/Streaming/Channels/101` | Hikvision | `cam1.mp4` | Security Camera (CCTV) Style Video in After Effects            |
| `camera-simulee-2` | `172.30.0.12` / `02:a6:05:00:00:02` | `rtsp://admin:argos-simulee@camera-simulee-2/cam/realmonitor?channel=1&subtype=0` | Dahua | `cam2.mp4` | 8MP 4K Dahua CCTV System Sample Video — Night Time             |
| `camera-simulee-3` | `172.30.0.13` / `02:a6:05:00:00:03` | `rtsp://camera-simulee-3/flux` | exotique (aucun chemin courant) | `cam3.mp4` | Example of Hi-Definition Video Surveillance of a Factory Floor |
| `camera-simulee-4` | `172.30.0.14` / `02:a6:05:00:00:04` | `rtsp://camera-simulee-4/Streaming/Channels/101` | Hikvision, en **H.265** | `cam4.mp4` | `cam1.mp4` réencodée en H.265 (voir plus bas) |
| `camera-simulee-5` | `172.30.0.15` / `02:a6:05:00:00:05` | `rtsp://camera-simulee-5/Streaming/Channels/101` | Hikvision | `cam3.mp4` | la même vidéo que `camera-simulee-3` |
| `camera-simulee-6` | `172.30.0.16` / `02:a6:05:00:00:06` | `rtsp://camera-simulee-6/Streaming/Channels/101` | Hikvision, en **H.265**, audio en avance | `cam4.mp4` | la même vidéo que `camera-simulee-4` |

`camera-simulee-4` annonce aussi une **piste audio** PCM 16 bits 8 kHz mono (un souffle, `AUDIO_IPCM` dans `compose.simulation.yaml`, générée par [`diffuser.sh`](diffuser.sh)), comme la caméra H.265 réelle du bug #141 : ses Segments portent une piste `ipcm`, que la Relecture retire ([ADR 0013](../../docs/adr/0013-relecture-des-enregistrements.md)).

`camera-simulee-6` reproduit **Cam 01** : sa piste audio G.711 est horodatée en avance sur sa vidéo (voir [plus bas](#audio-en-avance-camera-simulee-6)).

Les Caméras simulées 2, 4 et 5 répondent aussi en **ONVIF** (Réglages de la Caméra) : voir [`simulation/onvif/`](../../simulation/onvif/README.md). La 5 est « NTP paresseux » : calée sur le Site, son horloge dérive quand même.

## Date incrustée des Caméras simulées ONVIF

Les 1 et 3 diffusent leur vidéo **sans réencodage** (`-c copy`). Les 2, 4 et 5 incrustent en bas à gauche la date et l'heure de leur horloge ONVIF (7 minutes d'avance au démarrage, puis calée en NTP), que leur interface ONVIF écrit dans un fichier partagé (`FICHIER_DATE`, volume `camera-simulee-N-horloge`) et que `drawtext` relit à chaque image : leur vidéo est alors **réencodée à la volée** dans son codec (H.264 pour la 2 et la 5, H.265 `hvc1` pour la 4), `ultrafast`, keyframe toutes les 2 s, sans B-frames. L'image des Caméras simulées ([`Dockerfile`](Dockerfile)) est `bluenviron/mediamtx:1.21.1-ffmpeg` plus une police (DejaVu).

## Audio en avance (`camera-simulee-6`)

Cam 01, la caméra H.265 des tests humains de la V1.1.0, horodate son audio G.711 environ 14 s en avance sur sa vidéo. Le pont ouvre alors chaque Segment à l’heure de l’audio et jette la vidéo arrivée « trop tard » (`sample of track 1 received too late, discarding`, track 1 = la vidéo) : chaque Segment perd ~14 s de vidéo à son début, image clé comprise, et sa vidéo commence par des images P ([ADR 0018](../../docs/adr/0018-relecture-continue-fenetre-glissante.md), « Un Segment par fenêtre »). `camera-simulee-6` reproduit ce cas, avec sa propre configuration ([`camera-simulee-audio-en-avance.yml`](camera-simulee-audio-en-avance.yml)) et sa propre diffusion ([`diffuser-audio-en-avance.sh`](diffuser-audio-en-avance.sh)) :

- **vidéo** : `cam4.mp4` (H.265), l’heure locale de l’hôte incrustée en bas à gauche (fuseau de `/etc/localtime`, comme la Timeline), réencodée à la volée ;
- **audio** : un souffle G.711 µ-law 8 kHz mono, dont l’horodatage court deux fois plus vite que l’heure réelle pendant ses `AVANCE_AUDIO_S` (14) premières secondes, puis à l’heure : il finit en avance d’autant.

Pourquoi pas un seul ffmpeg (#172) : le pont aligne les pistes à l’arrivée de leur premier paquet, si bien qu’un écart constant (`-itsoffset`, `setpts` fixe) s’efface ; seul compte un écart qui se **creuse pendant sa lecture**. Et dans un seul ffmpeg, l’ordonnanceur freine la piste en avance pour la garder alignée sur l’autre. Chaque piste a donc son ffmpeg, qui l’envoie en RTP sur `127.0.0.1:5004`, où MediaMTX les réunit (`source: udp+rtp`). Le chemin ne s’ouvre qu’à la demande d’un lecteur (le pont, la sonde, l’essai, le healthcheck) et se referme 1 s après le dernier ; l’audio repart à chaque ouverture. L’avance se prend donc sous les yeux du lecteur qui a ouvert le chemin : un lecteur qui le rejoint déjà ouvert n’en voit qu’une part.

Au début d’un enregistrement, le temps que l’audio prenne son avance, le pont se recale quelques fois (`detected drift between recording duration and absolute time, resetting`) et coupe des Segments courts. Ensuite, chaque Segment dure ~1 min + 14 s d’heure réelle, pour ~1 min de vidéo.

### Lancer pour les tests humains

1. `docker compose -f compose.yaml -f compose.simulation.yaml up -d --build --wait` (comme toute la simulation).
2. Déclarer la Caméra (Administration) : `rtsp://camera-simulee-6/Streaming/Channels/101`, sans identifiants, puis allumer son **Enregistrement**. Au besoin, éteindre puis rallumer l’Enregistrement d’une Caméra déjà déclarée, pour que le pont rouvre le chemin et que l’audio reprenne son avance.
3. Attendre quelques minutes : plusieurs Segments fermés après la première minute.
4. Vérifier, au besoin, dans les journaux du pont : `docker compose logs mediamtx | grep "received too late"` (lignes `sample of track 1`).
5. Relecture de la Caméra : lire à ×1 une Plage sur plusieurs Segments ; l’heure incrustée de l’image suit l’**Instant lu** (à la seconde près, à l’image clé près), sans « Enregistrement indisponible » ni erreur au passage d’un Segment à l’autre. Les ~14 s jetées au début de chaque Segment sont sautées (limite connue de l’ADR 0018).

## Identifiants de `camera-simulee-2`

`camera-simulee-2` exige, comme beaucoup de vraies caméras, un identifiant et un mot de passe pour lire le Flux :

- identifiant : `admin`
- mot de passe : `argos-simulee`

Identifiants **de dev**, publics dans le dépôt (définis dans `compose.simulation.yaml`). Sans eux, ou avec un mauvais mot de passe, la Caméra répond `401 Unauthorized`, et une Caméra déclarée sans eux reste `offline`. Une requête `OPTIONS` sans identifiants reçoit quand même une réponse RTSP.

## Format attendu

- H.264 (`cam4.mp4` : H.265, tag `hvc1`), 1280×720, 15 i/s, **sans audio** (celui de `camera-simulee-4` et de `camera-simulee-6` est généré à la diffusion), sans B-frames
- Keyframe ~2 s, ≤ 50 Mo
- Diffusion en **copie de flux** (`-c copy`), sans réencodage à la volée, sauf pour incruster la date des Caméras simulées ONVIF et l’heure de `camera-simulee-6`

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
