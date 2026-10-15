<p align="center">
  <img src="docs/img/readme-banniere.jpg" alt="ArgOS" width="480" />
</p>

<!-- sync:stats-commits -->
<p align="center">
  <img src="https://img.shields.io/badge/commits_main-12-c8102e?style=for-the-badge" alt="12 commits sur main" />
  <img src="https://img.shields.io/badge/commits_PR_(historique)-70-1e3a5f?style=for-the-badge" alt="70 commits dans les PR mergées" />
</p>
<!-- /sync:stats-commits -->

# Plateforme de vidéosurveillance IP auto-hébergée

**ArgOS** est conçue pour rester générique et multi-marques : caméras RTSP/ONVIF, enregistrement, live, événements, puis détection et PTZ au fil des versions. Le nom évoque à la fois le chien d’Ulysse et Argos Panoptès (la vigilance à plusieurs yeux). Le projet est né d’un besoin de surveillance locale sur une grande propriété ; l’objectif logiciel est un produit self-hosted, sans dépendance cloud propriétaire.

## Documentation fonctionnelle et technique

<p align="center">
  <a href="https://ulyssoulv.github.io/ArgOS/">
    <img src="https://img.shields.io/badge/Ouvrir_la_documentation-GitHub_Pages-c8102e?style=for-the-badge" alt="Ouvrir la documentation" />
  </a>
</p>

Publiée par GitHub Pages à chaque merge sur `main` qui touche `docs/` ou `docs-site/`, et à chaque release.

## Quoi

Version **0.1.0** : trois **Caméras simulées** (`cam1`, `cam2`, `cam3`). MediaMTX diffuse en boucle une vidéo de dev par Caméra (H.264 1280×720, sans réencodage), joignable en RTSP et visible dans un navigateur (HLS, WebRTC), en local et sur le réseau local.

Version **0.2.0** : l’**API du Site** (FastAPI + PostgreSQL). L’Administrateur s’y connecte, gère les Caméras du Site, et l’API sonde leur état (`unknown` / `online` / `offline`).

Version **0.3.0** : l’**UI** (React, conteneur `web`). L’Administrateur se connecte sur `http://localhost:8080` (`https://localhost` depuis la 0.6.1), gère les Caméras dans l’onglet **Administration** et regarde leur Flux en WebRTC dans l’onglet **Live**, une Caméra active à la fois. MediaMTX sert de **pont** : l’API lui fait relayer toute Caméra active sur un chemin `camera-<id>`.

Version **0.4.0** : les Caméras simulées deviennent trois hôtes distincts (`camera-simulee-1` à `-3`, RTSP sur le port 554, l’une protégée par un identifiant), déclarés par un fichier Compose de simulation, `compose.simulation.yaml`, absent de la prod. Depuis l’Administration, une **Détection** cherche sur le réseau du Site les hôtes qui répondent en RTSP et les liste comme **Candidats** (voir [Réseau et Détection](docs/cameras/reseau-et-detection.md)).

Version **0.4.1** : **Ajouter** sur un Candidat, ou **Ajouter par adresse IP**, fait chercher son Flux par ArgOS sur les chemins courants des caméras, demande un mot de passe ou un chemin seulement s’il le faut, et montre l’**Aperçu** avant d’ajouter la Caméra : plus d’URL RTSP à écrire (voir [Ajouter une Caméra](docs/cameras/ajouter-une-camera.md)). Voir la [feuille de route de dev](docs/dev/feuille-de-route/feuille-de-route-dev.md).

Version **0.4.2** : ArgOS reconnaît l’**Appareil** de chaque Caméra par son **adresse MAC** (affichée au format `aa:bb:cc:dd:ee:ff` sur les Candidats, les Caméras et l’Aperçu). Une Détection qui retrouve un Appareil connu à une autre IP met à jour seule l’URL RTSP de ses Caméras (**adresse mise à jour**) ; une Caméra dont l’IP répond avec une autre MAC passe `offline` (**autre appareil à cette adresse**) et n’est plus relayée. **Filtrer par MAC** retrouve parmi les Candidats la caméra de l’étiquette. En prod Linux, l’API rejoint pour cela le réseau des caméras (macvlan, `compose.reseau-cameras.yaml`)  (voir [Réseau et Détection](docs/cameras/reseau-et-detection.md)).

Version **0.5.0** : les Caméras **H.265** (HEVC) se voient dans le Live et l’Aperçu, **sans réencodage**. ArgOS retient le **codec** de chaque Caméra (relevé à l’ajout, suivi par la sonde, affiché dans l’Administration) et choisit le transport d’après lui : WebRTC pour le H.264, **LL-HLS** pour le H.265, décodé par le navigateur (voir la documentation). Une quatrième Caméra simulée, `camera-simulee-4`, diffuse en H.265.

Version **0.6.0** : chaque Caméra active a des **Réglages** dans l’Administration. ArgOS lit la caméra par **ONVIF**, sans son interface web ni le cloud du fabricant, et règle ses **Incrustations** (texte, coin et affichage du nom et de la date et heure) et son **Horloge** (fuseau, mise à l’heure du Site), puis relit la caméra et dit, champ par champ, si le réglage est **pris**, **pas pris** ou **refusé**. Rien de ces réglages n’est gardé en base ; seul le port ONVIF trouvé est retenu. Les Caméras simulées 2 et 4 répondent en ONVIF (voir [Paramétrer une Caméra](docs/cameras/parametrer-une-camera.md#6-les-réglages-de-la-caméra-dans-argos)).

Version **0.6.1** : le Site n’est plus servi qu’en **HTTPS**, sous une seule adresse, **`https://<IP du Site>`** : UI, API et Live passent par le nginx de `web`, et les anciens ports HTTP (`8000`, `8888`, `8889`) sont fermés ; `http://…:8080` redirige vers HTTPS. Le certificat est signé par l’**Autorité du Site**, créée par ArgOS au premier lancement et installée une fois par poste ; un Administrateur qui a son propre certificat peut le déposer à la place (voir [Installer l’Autorité du Site](docs/features/reseau/installer-l-autorite-du-site.md) et le [schéma du réseau](docs/features/reseau/schema-flux.md)).

Version **0.6.2** : regarder une Caméra passe par la **connexion** d’ArgOS. Le Live et l’Aperçu (WebRTC et HLS) ne sont relayés qu’à une **session** valide (`401` sinon), et l’UI revient à la connexion quand un Flux est refusé. Le RTSP du pont (`8554`) n’est plus publié sur l’hôte : il n’est plus lisible depuis le réseau local (en dev, la simulation le republie sur `127.0.0.1:8554` seulement). Un Live WebRTC déjà ouvert continue après la déconnexion (voir [sécurité](docs/securite.md), [ADR 0006](docs/adr/0006-flux-authentifies-par-nginx.md)).

## Prérequis

- Docker (Docker Desktop sur Mac) avec Docker Compose
- Pour `/t` seulement : [uv](https://docs.astral.sh/uv/) (Python ≥ 3.12) et Chromium pour Playwright
- Pour lancer le front en dev seulement : Node 24 (npm)

Rien d’autre : ffmpeg / ffprobe tournent dans des conteneurs.

## Configurer `.env`

`.env` est ignoré par git : les secrets n’entrent jamais dans le dépôt. Les clés sont décrites dans `.env.example`.

```bash
cp .env.example .env
# dans .env : ARGOS_IDENTIFIANT=… et ARGOS_MOT_DE_PASSE=… (mot de passe long recommandé)
```

`ARGOS_IDENTIFIANT` et `ARGOS_MOT_DE_PASSE` sont le compte de l’Administrateur : sans eux, l’API ne démarre pas (il n’y a pas de compte par défaut). En dev local, un compte de test suffit (par exemple `ARGOS_IDENTIFIANT=administrateur`, `ARGOS_MOT_DE_PASSE=argos-dev-phrase-de-passe-de-test`) ; jamais sur une vraie installation. Pour le lanceur macOS, le mot de passe ne doit contenir ni espace ni guillemet (`.env` y est lu par le shell).

## Lanceur macOS

Double-cliquer sur **`lancer-argos.command`** à la racine du dépôt. Il :

1. crée `.env` à partir de `.env.example` s’il manque, et demande le compte de l’Administrateur s’il n’est pas défini (mot de passe vide = un mot de passe généré, affiché une fois et écrit dans `.env`) ; puis lance `scripts/cameras/configurer-detection.sh` (sous-réseaux de la Détection, prise demandée au premier lancement s’il y en a plusieurs) ;
2. démarre Docker Desktop s’il ne tourne pas, et attend que le moteur réponde ;
3. lance la stack **avec la simulation** : `docker compose -f compose.yaml -f compose.simulation.yaml up -d --build --wait` ;
4. affiche l’empreinte SHA-256 de l’Autorité du Site (`/argos-ca.crt`) et, si elle n’est pas dans le trousseau de session, demande (o/n) avant de l’y ajouter (`scripts/autorite/ajouter-au-trousseau.sh` ; macOS demande le mot de passe) ; rien à installer avec un certificat fourni ;
5. ouvre une fenêtre Terminal avec les logs de la stack et l’UI sur `https://localhost`.

Fermer les fenêtres n’arrête pas la stack : `docker compose -f compose.yaml -f compose.simulation.yaml down`. Si le double-clic ne fait rien (dépôt téléchargé en `.zip` plutôt que cloné), lancer une fois `chmod +x lancer-argos.command` dans un Terminal à la racine du dépôt, ou faire clic droit → *Ouvrir* pour passer Gatekeeper.

## Ouvrir le Site depuis un autre poste

Le Site est à l’adresse **`https://<IP du Site>`** : déclarer cette IP dans `.env` (`MTX_WEBRTCADDITIONALHOSTS`), sans quoi le certificat ne la nomme pas et seule la machine hôte reconnaît le Site.

Sur chaque poste (Mac, iPhone, PC, Android), une fois :

1. télécharger l’Autorité du Site sur **`http://<IP du Site>/argos-ca.crt`** ;
2. comparer son empreinte SHA-256 avec celle affichée au lancement (`docker compose logs certificats | grep Empreinte`, ou la fenêtre du lanceur) ;
3. l’installer et l’approuver, pas à pas : [Installer l’Autorité du Site](docs/features/reseau/installer-l-autorite-du-site.md).

Ne jamais passer outre un avertissement du navigateur. Perdre le volume Docker `autorite` (`docker compose down -v`) crée une nouvelle Autorité, à réinstaller sur tous les postes.
