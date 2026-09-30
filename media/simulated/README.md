# Vidéos des Caméras simulées

Fichiers de **dev** pour MediaMTX (`cam1`, `cam2`, `cam3`). Ce ne sont pas des enregistrements produit : à remplacer plus tard par de vraies caméras IP.

## Fichiers

| Fichier     | Rôle                          | Origine (source déposée)                                      |
|-------------|-------------------------------|----------------------------------------------------------------|
| `cam1.mp4`  | Caméra simulée `cam1`         | Security Camera (CCTV) Style Video in After Effects            |
| `cam2.mp4`  | Caméra simulée `cam2`         | 8MP 4K Dahua CCTV System Sample Video — Night Time             |
| `cam3.mp4`  | Caméra simulée `cam3`         | Example of Hi-Definition Video Surveillance of a Factory Floor |

## Format attendu (après conversion, avant commit final de la stack)

- H.264, 1280×720, 15 i/s, **sans audio**
- Keyframe ~2 s, ≤ 50 Mo
- Diffusion MediaMTX en **copie de flux** (`-c copy`), sans réencodage à la volée

Les fichiers déposés ici peuvent encore être au format source ; la conversion est faite une fois (ffmpeg en conteneur) pendant l’implémentation 0.1.0.

## Conversion (référence)

```bash
docker run --rm -v "$PWD":/v linuxserver/ffmpeg:version-7.1-cli \
  -y -i /v/camN.mp4 \
  -an -c:v libx264 -pix_fmt yuv420p -r 15 -g 30 -keyint_min 30 -sc_threshold 0 \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -preset medium -crf 23 \
  /v/camN.converted.mp4
# puis remplacer camN.mp4 par la version convertie
```
