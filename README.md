# ArgOS

Plateforme de **vidéosurveillance IP auto-hébergée**, conçue pour rester générique et multi-marques : caméras RTSP/ONVIF, enregistrement, live, événements, puis détection et PTZ au fil des versions.

Le nom évoque à la fois le chien d’Ulysse et Argos Panoptès (la vigilance à plusieurs yeux). Le projet est né d’un besoin de surveillance locale sur une grande propriété ; l’objectif logiciel est un produit self-hosted, sans dépendance cloud propriétaire.

## Quoi

Version **0.1.0** : trois **Caméras simulées** (`cam1`, `cam2`, `cam3`). MediaMTX diffuse en boucle une vidéo de dev par Caméra (H.264 1280×720, sans réencodage), joignable en RTSP et visible dans un navigateur (HLS, WebRTC), en local et sur le réseau local. Pas encore d’API Site ni d’UI : voir la [feuille de route de dev](docs/dev/feuille-de-route-dev.md).

## Prérequis

- Docker (Docker Desktop sur Mac) avec Docker Compose
- Pour `/t` seulement : [uv](https://docs.astral.sh/uv/) (Python ≥ 3.12)

Rien d’autre : ffmpeg / ffprobe tournent dans des conteneurs.

## Lancer / arrêter

```bash
docker compose up -d --wait   # lance les Caméras simulées
docker compose down           # arrête
```

## Flux des Caméras simulées

Remplacer `localhost` par l’IP de la machine pour y accéder depuis un autre appareil du réseau local.

| Caméra simulée | RTSP                              | HLS (navigateur)              | WebRTC (navigateur)           |
|----------------|-----------------------------------|-------------------------------|-------------------------------|
| `cam1`         | `rtsp://localhost:8554/cam1`      | `http://localhost:8888/cam1`  | `http://localhost:8889/cam1`  |
| `cam2`         | `rtsp://localhost:8554/cam2`      | `http://localhost:8888/cam2`  | `http://localhost:8889/cam2`  |
| `cam3`         | `rtsp://localhost:8554/cam3`      | `http://localhost:8888/cam3`  | `http://localhost:8889/cam3`  |

Ports : RTSP 8554/tcp, HLS 8888/tcp, WebRTC 8889/tcp + 8189/udp (ICE). Pas d’authentification sur les Flux.

### WebRTC sur le réseau local

HLS marche sur le réseau local sans réglage. WebRTC doit annoncer l’IP de la machine aux navigateurs (Docker Desktop masque l’IP réelle) :

```bash
cp .env.example .env                       # si .env n’existe pas encore (il est ignoré par git)
ipconfig getifaddr en0                     # IP de la machine sur Mac (Linux : hostname -I)
# dans .env : MTX_WEBRTCADDITIONALHOSTS=192.168.1.20   (plusieurs IP : séparées par des virgules)
docker compose up -d --wait                # recrée le conteneur avec la nouvelle valeur
```

Puis ouvrir `http://<IP>:8889/camN` depuis un téléphone ou une tablette du même réseau.

## Comment circulent les Flux

Pour chaque Caméra simulée, MediaMTX lance un ffmpeg qui lit `camN.mp4` au rythme réel, en boucle, **sans réencodage** (`-c copy`), et le publie en RTSP sur le chemin `camN`. MediaMTX joue alors le rôle d’une caméra IP. Il ressert les **mêmes images H.264** sous trois emballages :

| Protocole | Chemin | Retard | Pour qui |
|-----------|--------|--------|----------|
| RTSP (8554/tcp) | une connexion TCP ; paquets RTP en continu | direct | VLC, ffprobe, backend |
| HLS (8888/tcp) | page + lecteur JS ; playlist `index.m3u8` relue en boucle ; morceaux MP4 d’environ 1 s téléchargés en HTTP | plusieurs secondes | navigateur |
| WebRTC (8889/tcp + 8189/udp) | page + lecteur JS ; négociation HTTP (`/camN/whep`), où MediaMTX annonce les adresses où le joindre (candidats ICE) ; puis RTP chiffré en UDP | < 1 s | navigateur (Live) |

Les navigateurs ne lisent pas le RTSP : HLS et WebRTC servent de pont. WebRTC a besoin de l’IP de la machine dans `.env`, parce que sous Docker Desktop, MediaMTX ne voit que son IP interne de conteneur et ne peut pas annoncer celle du réseau local.

### Rôle de chaque protocole dans ArgOS

```
Caméras (réelles ou simulées) ──RTSP──▶ backend (état online/offline, plus tard enregistrement, IA)
                               └─RTSP──▶ MediaMTX ──WebRTC (ou HLS)──▶ navigateur (onglet Live)
```

- **RTSP, en entrée** : protocole des caméras IP. Une Caméra est identifiée par son URL RTSP (voir `CONTEXT.md`). Ajouter une Caméra au Site (0.2.0), c’est d’abord enregistrer cette URL.
- **WebRTC, en sortie** : candidat pour le Live (0.3.0 / 1.0.0), grâce à son faible retard. HLS reste une solution de secours.
- **Contrat de la 0.1.0** : 3 URL RTSP stables, en H.264 1280×720, visibles dans un navigateur. L’API et l’UI se développent contre ce contrat sans matériel ; les vraies caméras le respectent aussi.

Pas encore décidé (à trancher à l’ouverture de la 0.2.0 / 0.3.0) : WebRTC ou HLS pour le Live ; et si l’API Site ajoute elle-même les Caméras comme chemins MediaMTX (API de contrôle de MediaMTX, source = URL RTSP de la caméra), avec un MediaMTX simulateur et un MediaMTX pont séparés ou non.

## Vérifier un Flux en CLI

```bash
docker run --rm --add-host host.docker.internal:host-gateway \
  --entrypoint ffprobe linuxserver/ffmpeg:version-7.1-cli \
  -v error -rtsp_transport tcp -select_streams v:0 \
  -show_entries stream=codec_name,width,height -of default=nw=1 \
  rtsp://host.docker.internal:8554/cam1
```

Attendu : `codec_name=h264`, `width=1280`, `height=720`.

## Tests

`/t` (skill `lancer-tests`) lance pytest dans `tests/flux/` ; à la main :

```bash
cd tests/flux && uv run pytest
```

Les tests démarrent la stack si elle ne tourne pas, puis vérifient chaque Caméra simulée vue de l’extérieur : RTSP en H.264 1280×720 décodable, playlist HLS, et refus de `cam404`. WebRTC n’est pas testé automatiquement.

## Structure

```
compose.yaml              Stack Docker Compose (MediaMTX)
.env.example              Clés de .env (WebRTC réseau local, Sonar)
media/mediamtx.yml        Config MediaMTX : chemins cam1..cam3, ports
media/simulated/          Vidéos des Caméras simulées (+ README : format, conversion)
tests/flux/               Tests de bout en bout des Flux (pytest, uv)
docs/dev/                 Feuille de route de dev
docs/specs/               Specs de version et contexte initial
CONTEXT.md                Glossaire (Caméra, Flux, Caméra simulée)
AGENTS.md, agents/        Cycle de dev avec les agents, skills, rôles
```

## Principes

- Standards ouverts (RTSP, ONVIF, H.264/H.265, Docker)
- Caméras abstraites (réelles ou simulées via MediaMTX) — pas de lock-in fabricant
- Modularité : chaque brique testable ; IA, ONVIF, PTZ optionnels
- PostgreSQL pour les données ; UI web React (navigateur / kiosque) prévue
- Intent open source pendant le développement (licence formelle à la première release)

Hypothèses et notes de conception du moment (non figées) : [docs/specs/contexte-initial.md](docs/specs/contexte-initial.md).

## Développement avec les agents

Voir [AGENTS.md](AGENTS.md) pour le cycle **Ouvre la version → implement → Finalise la version**, les tests (`/t`) et le quality gate (`/qg`).

## Licence

À définir à la première release. Développement mené dans un esprit open source.
