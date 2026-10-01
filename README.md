# ArgOS

Plateforme de **vidéosurveillance IP auto-hébergée**, conçue pour rester générique et multi-marques : caméras RTSP/ONVIF, enregistrement, live, événements, puis détection et PTZ au fil des versions.

Le nom évoque à la fois le chien d’Ulysse et Argos Panoptès (la vigilance à plusieurs yeux). Le projet est né d’un besoin de surveillance locale sur une grande propriété ; l’objectif logiciel est un produit self-hosted, sans dépendance cloud propriétaire.

## Quoi

Version **0.1.0** : trois **Caméras simulées** (`cam1`, `cam2`, `cam3`). MediaMTX diffuse en boucle une vidéo de dev par Caméra (H.264 1280×720, sans réencodage), joignable en RTSP et visible dans un navigateur (HLS, WebRTC), en local et sur le réseau local.

Version **0.2.0** : l’**API du Site** (FastAPI + PostgreSQL). L’Administrateur s’y connecte, gère les Caméras du Site, et l’API sonde leur état (`unknown` / `online` / `offline`).

Version **0.3.0** (en cours) : l’**UI** (React, conteneur `web`). L’Administrateur se connecte sur `http://localhost:8080`, gère les Caméras dans l’onglet **Administration** et regarde leur Flux en WebRTC dans l’onglet **Live**, une Caméra active à la fois. MediaMTX sert de **pont** : l’API lui fait relayer toute Caméra active sur un chemin `camera-<id>`. Voir la [feuille de route de dev](docs/dev/feuille-de-route-dev.md).

## Prérequis

- Docker (Docker Desktop sur Mac) avec Docker Compose
- Pour `/t` seulement : [uv](https://docs.astral.sh/uv/) (Python ≥ 3.12) et Chromium pour Playwright (voir [Tests](#tests))
- Pour lancer le front en dev seulement : Node 24 (npm)

Rien d’autre : ffmpeg / ffprobe tournent dans des conteneurs.

## Configurer `.env`

`.env` est ignoré par git : les secrets n’entrent jamais dans le dépôt. Les clés sont décrites dans `.env.example`.

```bash
cp .env.example .env
# dans .env : ARGOS_IDENTIFIANT=… et ARGOS_MOT_DE_PASSE=… (mot de passe long recommandé)
```

`ARGOS_IDENTIFIANT` et `ARGOS_MOT_DE_PASSE` sont le compte de l’Administrateur : sans eux, l’API ne démarre pas (il n’y a pas de compte par défaut). En dev local, un compte de test suffit (par exemple `ARGOS_IDENTIFIANT=administrateur`, `ARGOS_MOT_DE_PASSE=argos-dev-phrase-de-passe-de-test`) ; jamais sur une vraie installation. Pour le protocole de lancement ci-dessous, le mot de passe ne doit contenir ni espace ni guillemet (`.env` y est lu par le shell).

## Protocole de lancement

Tout se lance depuis la racine du dépôt. Les commandes curl lisent l’identifiant et le mot de passe dans `.env` (voir ci-dessus) : rien à recopier à la main.

**1. Démarrer la stack**

```bash
docker compose up -d --build --wait   # Caméras simulées (mediamtx), API (api), base (db) et UI (web)
docker compose ps                      # attendu : api, db, mediamtx et web « healthy »
```

Au premier lancement, Docker construit les images de l’API et de l’UI. Le schéma de la base est appliqué au démarrage de `api` (migrations Alembic), sans étape manuelle. Si `api` ne démarre pas : `docker compose logs api` (identifiants absents ou réglage de sonde invalide dans `.env`).

**2. Se connecter en tant qu’Administrateur**

```bash
set -a; . ./.env; set +a   # charge ARGOS_IDENTIFIANT et ARGOS_MOT_DE_PASSE dans le shell
curl -s -o /dev/null -w '%{http_code}\n' -c cookies.txt -X POST http://localhost:8000/api/session \
  -H 'Content-Type: application/json' \
  -d "{\"identifiant\": \"$ARGOS_IDENTIFIANT\", \"mot_de_passe\": \"$ARGOS_MOT_DE_PASSE\"}"
curl -s -b cookies.txt http://localhost:8000/api/moi   # attendu : {"identifiant":"…"}
```

Attendu : `204`. Un `401` veut dire que l’identifiant ou le mot de passe ne correspond pas à celui de l’API : `.env` a changé depuis le démarrage (refaire l’étape 1, qui recrée `api`), ou `. ./.env` n’a pas été lancé depuis la racine du dépôt. Un `429` : trop d’échecs, attendre 15 min ou `docker compose restart api`. Une connexion ratée vide `cookies.txt`.

`cookies.txt` garde la session (24 h) pour les commandes suivantes ; il est ignoré par git. Sans terminal : ouvrir **http://localhost:8000/api/docs**, appeler `POST /api/session` (« Try it out »), le navigateur garde le cookie pour les autres routes.

**3. Déclarer les trois Caméras simulées** (une seule fois : la base les garde ; relancer renvoie `409`)

```bash
for n in 1 2 3; do
  curl -b cookies.txt -X POST http://localhost:8000/api/cameras \
    -H 'Content-Type: application/json' \
    -d "{\"nom\": \"Caméra simulée $n\", \"url_rtsp\": \"rtsp://mediamtx:8554/cam$n\"}"
done
```

**4. Suivre l’état des Caméras** (dans un second terminal, **depuis la racine du dépôt** : c’est là qu’est `cookies.txt` ; Ctrl+C pour arrêter)

```bash
while true; do
  clear
  curl -s -b cookies.txt http://localhost:8000/api/cameras | python3 -c '
import json, sys
from datetime import datetime
try:
    cameras = json.load(sys.stdin)
except ValueError:
    sys.exit("API injoignable : la stack tourne-t-elle ? (étape 1)")
if not isinstance(cameras, list):
    sys.exit("Pas de session : lancer depuis la racine du dépôt, ou refaire l’étape 2")
ligne = "{:>4}  {:<22}{:<9}{:<11}{}"
print(ligne.format("id", "nom", "état", "vérifié à", "active"))
for c in cameras:
    verifie = c["etat_verifie_le"] and datetime.fromisoformat(c["etat_verifie_le"]).astimezone().strftime("%H:%M:%S")
    print(ligne.format(c["id"], c["nom"], c["etat"], verifie or "-", "oui" if c["active"] else "non"))'
  sleep 2
done
```

Attendu : les trois Caméras passent de `unknown` à `online` en 15 s au plus.

**5. Essais** (`<id>` = id affiché à l’étape 4)

| Essai | Commande | Attendu |
|---|---|---|
| Couper les Caméras simulées | `docker compose stop mediamtx` | toutes `offline` en 15 s au plus |
| Les rallumer | `docker compose start mediamtx` | retour à `online` |
| Changer l’URL | `curl -b cookies.txt -X PATCH http://localhost:8000/api/cameras/<id> -H 'Content-Type: application/json' -d '{"url_rtsp": "rtsp://mediamtx:8554/cam404"}'` | `unknown` tout de suite, puis `offline` |
| Désactiver | même `PATCH` avec `-d '{"active": false}'` | `unknown`, plus sondée |
| Réactiver | même `PATCH` avec `-d '{"active": true}'` | de nouveau `online` |
| Supprimer (désactivée d’abord) | `curl -b cookies.txt -X DELETE http://localhost:8000/api/cameras/<id>` | `204` ; `409` si la Caméra est encore active |

Les Flux eux-mêmes se regardent dans un navigateur : `http://localhost:8889/cam1` (voir [Flux des Caméras simulées](#flux-des-caméras-simulées)).

**6. Arrêter**

```bash
curl -b cookies.txt -X DELETE http://localhost:8000/api/session   # déconnexion (facultatif)
docker compose down      # arrête ; Caméras et sessions restent dans le volume donnees-db
docker compose down -v   # arrête et efface la base (repartir de zéro : refaire l’étape 3)
```

## UI

Ouvrir **http://localhost:8080** et se connecter avec `ARGOS_IDENTIFIANT` / `ARGOS_MOT_DE_PASSE` de `.env`. L’en-tête montre les onglets **Administration** et **Live**, l’identifiant connecté et le bouton **Déconnexion**. Une session absente ou expirée renvoie sur `/connexion`, puis à la page demandée après connexion.

### Administration

L’onglet **Administration** couvre toute la gestion des Caméras :

- la liste de toutes les Caméras (nom, emplacement, hôte:port, URL avec le mot de passe RTSP masqué, active ou désactivée, état `unknown` / `online` / `offline`, dernière vérification), rafraîchie toute seule toutes les 10 s ;
- **Nouvelle Caméra** : nom, URL RTSP, emplacement facultatif ;
- **Modifier** : nom, URL, emplacement. L’URL s’affiche masquée (`rtsp://user:***@…`) : la laisser telle quelle conserve le mot de passe RTSP enregistré ;
- un refus de l’API s’affiche dans le formulaire : nom ou URL déjà pris (`409`, Caméras désactivées comprises), URL qui n’est pas `rtsp://…` (`422`) ;
- **Désactiver** / **Réactiver** ;
- **Supprimer** : offert seulement sur une Caméra désactivée, après **Confirmer la suppression**.

**Déclarer les trois Caméras simulées depuis l’UI** (une seule fois : la base les garde). Dans **Nouvelle Caméra**, créer :

| Nom | URL RTSP |
|---|---|
| Caméra simulée 1 | `rtsp://mediamtx:8554/cam1` |
| Caméra simulée 2 | `rtsp://mediamtx:8554/cam2` |
| Caméra simulée 3 | `rtsp://mediamtx:8554/cam3` |

Elles passent `online` en 15 s au plus, sans recharger la page. Pourquoi `mediamtx` et pas `localhost` : voir [Ajouter les Caméras simulées](#ajouter-les-caméras-simulées).

Le conteneur `web` ne sert que les fichiers statiques. Le front appelle l’API sur **le même hôte que la page**, port 8000, avec le cookie de session (CORS avec credentials, voir [docs/securite.md](docs/securite.md#ui-et-api--deux-origines-cors-avec-credentials)) : le même build marche via `localhost` ou l’IP du réseau local. Pour ouvrir l’UI depuis un autre appareil (`http://<IP>:8080`), ajouter cette origine dans `.env`, puis `docker compose up -d --wait` :

```bash
ARGOS_ORIGINES_AUTORISEES=http://localhost:8080,http://localhost:5173,http://192.168.1.20:8080
```

### Live

L’onglet **Live** montre en grand le Flux d’**une** Caméra active à la fois, en WebRTC (moins d’une seconde de retard) :

- les Caméras actives sont prises dans l’ordre des noms ; le Live s’ouvre sur la première ;
- **Suivant** (ou la flèche droite) passe à la suivante, puis revient à la première après la dernière ;
- au-dessus de la vidéo : nom, emplacement et état de la Caméra (rafraîchi toutes les 10 s) ;
- aucune Caméra active : un message renvoie vers **Administration** ;
- la vidéo ne vient pas ou se coupe : **Flux indisponible**, puis nouvelle tentative toutes les 5 s. Une Caméra tout juste créée ou réactivée peut mettre jusqu’à 10 s à être relayée : le Live la rattrape seul.

Le front lit le Flux par un client **WHEP** : `POST http://<hôte>:8889/<chemin_flux>/whep` (offre SDP), puis la vidéo arrive dans un `<video>`. Pas d’iframe ni de HLS. Changer de Caméra ferme la connexion WebRTC précédente : une seule est ouverte à la fois. `<chemin_flux>` (`camera-<id>`) vient de l’API.

WebRTC fait passer la vidéo en **UDP 8189** : ce port doit être joignable depuis le navigateur. Pour regarder le Live depuis un autre appareil du réseau local, `MTX_WEBRTCADDITIONALHOSTS` doit contenir l’IP de la machine (voir [WebRTC sur le réseau local](#webrtc-sur-le-réseau-local)), en plus de l’origine dans `ARGOS_ORIGINES_AUTORISEES`.

### Front en dev

Contre la stack lancée (étape 1), sans reconstruire l’image :

```bash
cd web
npm install
npm run dev     # http://localhost:5173, rechargement à chaud
```

`http://localhost:5173` est autorisée par défaut. Port de l’API différent : `VITE_ARGOS_PORT_API=8001 npm run dev` (vaut aussi pour `npm run build`).

## API du Site

Écoute sur `http://localhost:8000` (HTTP simple : voir [docs/securite.md](docs/securite.md)). Documentation OpenAPI interactive : **`http://localhost:8000/api/docs`**.

| Route | Effet |
|-------|-------|
| `POST /api/session` `{"identifiant", "mot_de_passe"}` | Connexion : `204` + cookie de session `argos_session` (`HttpOnly`, `SameSite=Lax`) ; `401` si l’identifiant ou le mot de passe est faux |
| `GET /api/moi` | `{"identifiant"}` de l’Administrateur connecté ; `401` sans session valide |
| `DELETE /api/session` | Déconnexion : `204`, la session est supprimée côté serveur |
| `GET` / `POST /api/cameras` | Liste / création d’une Caméra `{"nom", "url_rtsp", "emplacement"?}` (mot de passe RTSP masqué en `***` dans toutes les réponses) |
| `GET` / `PATCH` / `DELETE /api/cameras/{id}` | Lecture, modification partielle (`"active": false` désactive), suppression d’une Caméra désactivée |

Les sessions sont stockées en base : elles survivent à un redémarrage de `api`.

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/session \
  -H 'Content-Type: application/json' \
  -d '{"identifiant": "…", "mot_de_passe": "…"}'
curl -b cookies.txt http://localhost:8000/api/moi
curl -b cookies.txt -X DELETE http://localhost:8000/api/session
```

PostgreSQL n’a aucun port publié : seul `api` le joint. Pour l’inspecter : `docker compose exec db psql -U argos`.

### Ajouter les Caméras simulées

La base démarre vide : déclarer les Caméras simulées depuis l’onglet [Administration](#administration) de l’UI, ou avec l’étape 3 du [protocole de lancement](#protocole-de-lancement).

L’URL est `rtsp://mediamtx:8554/camN`, pas `rtsp://localhost:8554/camN` : c’est le conteneur `api` qui sonde la Caméra, et dans ce conteneur `localhost` désigne `api` lui-même. `mediamtx` est le nom du service MediaMTX sur le réseau interne de Docker Compose. Une vraie caméra se déclare avec son adresse sur le réseau local (`rtsp://user:motdepasse@192.168.1.50/...`).

### État des Caméras

L’API sonde chaque Caméra **active**, en parallèle, toutes les 10 s : session RTSP (identifiants de l’URL pris en charge), puis attente d’**au moins un paquet vidéo** pendant 5 s au plus. Reçu → `etat` passe à `online`, sinon à `offline` ; `etat_verifie_le` dit quand. Une Caméra nouvelle, dont l’URL vient de changer, ou désactivée (plus sondée) est `unknown`. Intervalle et délai se règlent dans `.env` (`ARGOS_SONDE_INTERVALLE_S`, `ARGOS_SONDE_DELAI_S`, voir `.env.example`).

`online` prouve que quelque chose diffuse de la vidéo à cette URL, pas que c’est la vraie caméra : voir [docs/securite.md](docs/securite.md#1-ce-que-prouve-létat-dune-caméra).

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

Puis ouvrir `http://<IP>:8889/camN` depuis un téléphone ou une tablette du même réseau. Le [Live](#live) de l’UI en a besoin aussi, avec l’UDP 8189 joignable.

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
- **WebRTC, en sortie** : protocole du Live (0.3.0), grâce à son faible retard. MediaMTX relaie chaque Caméra active sur `camera-<id>` ([ADR 0001](docs/adr/0001-mediamtx-en-pont.md)).
- **Contrat de la 0.1.0** : 3 URL RTSP stables, en H.264 1280×720, visibles dans un navigateur. L’API et l’UI se développent contre ce contrat sans matériel ; les vraies caméras le respectent aussi.

Décidé en 0.3.0 : le Live lit en WebRTC uniquement, et l’API ajoute elle-même chaque Caméra active comme chemin MediaMTX (API de contrôle, source = URL RTSP de la Caméra), dans le même MediaMTX que les Caméras simulées.

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

`/t` (skill `lancer-tests`) lance pytest dans chaque racine de tests (`tests/flux/`, `tests/api/`, `tests/regles-sessions/`, `tests/web/`) ; à la main :

```bash
cd tests/flux && uv run pytest
cd tests/api && uv run pytest
cd tests/regles-sessions && uv run pytest
cd tests/web && uv run pytest
```

`tests/web/` a besoin de Chromium pour Playwright, à installer une fois :

```bash
cd tests/web && uv sync && uv run playwright install chromium
```

- `tests/flux/` démarre la stack si elle ne tourne pas, puis vérifie chaque Caméra simulée vue de l’extérieur : RTSP en H.264 1280×720 décodable, playlist HLS, et refus de `cam404`. WebRTC n’est pas testé automatiquement.
- `tests/api/` lance `docker compose up -d --build --wait`, puis teste l’API en HTTP sur `localhost:8000` : connexion, `GET /api/moi`, déconnexion, mauvais identifiants, session conservée après `docker compose restart api`, `429` après 5 échecs (le test redémarre `api` avant et après pour remettre le compteur à zéro), `/api/docs`, gestion des Caméras, et leur état sondé (`online` sur `rtsp://mediamtx:8554/cam1`, `offline` sur une URL injoignable ou `cam404`, `unknown` après changement d’URL ou désactivation ; chaque attente d’état dure jusqu’à 40 s). Les identifiants sont lus dans `.env` ; s’ils manquent, les tests échouent tout de suite en disant quoi ajouter.
- `tests/web/` lance la stack comme `tests/api/`, puis pilote l’UI sur `http://localhost:8080` dans Chromium headless (pytest-playwright) : connexion réussie (identifiant dans l’en-tête), mauvais mot de passe (message, reste sur `/connexion` ; le test redémarre `api` ensuite pour remettre le frein à zéro), page connectée sans session renvoyée à `/connexion` puis retour à la page demandée, Déconnexion ; Administration : Caméra créée sur `cam1` qui apparaît puis passe `online` sans recharger, doublon de nom (`409`) et URL non `rtsp://` affichés dans le formulaire, emplacement modifié sans perdre le mot de passe RTSP, désactivation / réactivation, suppression d’une désactivée après confirmation (aucune suppression offerte sur une active) ; Live : première Caméra active par nom dont la `<video>` joue vraiment (`currentTime` qui avance), Suivant puis flèche droite qui font le tour en gardant une seule connexion WebRTC ouverte, message avec lien vers Administration sans Caméra active, « Flux indisponible » sur une URL injoignable. Les tests Live désactivent les Caméras actives existantes le temps du test, puis les réactivent. Les identifiants sont lus dans `.env` ; la base n’est jamais effacée : chaque test crée des Caméras aux noms uniques, puis les désactive et les supprime.
- `tests/api/` couvre aussi le CORS : origine autorisée → en-têtes avec credentials, autre origine → rien.
- `tests/regles-sessions/` monte l’application en processus, horloge et configuration injectées, contre un PostgreSQL de test jetable (même image que `db`, lancé par testcontainers ; Docker requis). Réservé aux règles impossibles à tester vite en HTTP : expiration à 24 h, fin du `429` après 15 min, sessions refusées après un changement de mot de passe, refus de démarrer sans identifiants.

## Structure

```
compose.yaml              Stack Docker Compose (mediamtx, api, db, web)
.env.example              Clés de .env (Administrateur, origines de l’UI, WebRTC réseau local, Sonar)
api/                      API du Site (FastAPI, uv) : argos_api/, migrations Alembic, Dockerfile
web/                      UI (React, Vite, TypeScript) : src/, Dockerfile (Node → nginx), nginx.conf
media/mediamtx.yml        Config MediaMTX : chemins cam1..cam3, ports
media/simulated/          Vidéos des Caméras simulées (+ README : format, conversion)
tests/flux/               Tests de bout en bout des Flux (pytest, uv)
tests/api/                Tests HTTP de l’API contre la stack lancée (pytest, httpx, uv)
tests/regles-sessions/    Tests en processus des règles de session (horloge et configuration injectées)
tests/web/                Tests de bout en bout de l’UI (pytest-playwright, Chromium headless)
docs/dev/                 Feuille de route de dev
docs/specs/               Specs de version et contexte initial
docs/securite.md          Sécurité : limites connues, exposition réseau, dettes
CONTEXT.md                Glossaire (Site, Administrateur, Caméra, Flux…)
AGENTS.md, agents/        Cycle de dev avec les agents, skills, rôles
```

## Principes

- Standards ouverts (RTSP, ONVIF, H.264/H.265, Docker)
- Caméras abstraites (réelles ou simulées via MediaMTX) — pas de lock-in fabricant
- Modularité : chaque brique testable ; IA, ONVIF, PTZ optionnels
- PostgreSQL pour les données ; UI web React (navigateur / kiosque)
- Intent open source pendant le développement (licence formelle à la première release)

Hypothèses et notes de conception du moment (non figées) : [docs/specs/contexte-initial.md](docs/specs/contexte-initial.md).

## Développement avec les agents

Voir [AGENTS.md](AGENTS.md) pour le cycle **Ouvre la version → implement → Finalise la version**, les tests (`/t`) et le quality gate (`/qg`).

## Licence

À définir à la première release. Développement mené dans un esprit open source.
