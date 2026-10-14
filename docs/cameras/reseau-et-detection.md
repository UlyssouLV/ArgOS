# Réseau du Site et Détection des Caméras

Comprendre, et pouvoir expliquer, comment les Caméras sont reliées à la machine qui héberge ArgOS, et ce que fait le bouton **Détecter des Caméras** de l’Administration. Écrit pour quelqu’un qui n’est pas spécialiste du réseau.

Pour ajouter un Candidat comme Caméra : [Ajouter une Caméra](ajouter-une-camera.md). Reconnaître une caméra qui change d’IP (adresse MAC, réseau des caméras) : § 9 et § 10. Pour aller plus loin : [ADR 0002](../adr/0002-detection-depuis-le-reseau-bridge.md) (pourquoi les sous-réseaux sont déclarés), [ADR 0003](../adr/0003-macvlan-sur-la-prise-des-cameras.md) (pourquoi l’API rejoint le réseau des caméras), [sécurité](../securite.md#détection--argos-agit-sur-le-réseau) (ce que la Détection envoie), [schéma des Flux](../dev/schema-flux.md).

## 1. Adresse IP, sous-réseau, notation `/24`

Chaque appareil branché sur un réseau (la machine ArgOS, une caméra, un téléphone) a une **adresse IP**, par exemple `192.168.1.20` : quatre nombres de 0 à 255.

Un **sous-réseau** est un groupe d’adresses qui se parlent directement, sans passer par un routeur : en pratique, les appareils branchés sur le même switch, ou sur la même box. On l’écrit avec la **notation CIDR** : `192.168.1.0/24`.

- Le nombre après la barre dit combien de bits, en partant de la gauche, sont **fixes** pour tout le sous-réseau. Une adresse IPv4 fait 32 bits ; `/24` fixe les 24 premiers, soit les trois premiers nombres (`192.168.1`). Le dernier nombre varie : `192.168.1.0` à `192.168.1.255`, **256 adresses**.
- Deux d’entre elles sont réservées (la première désigne le réseau, la dernière sert à parler à tous) : il reste **254 appareils** possibles, de `.1` à `.254`.
- Plus le nombre est petit, plus le sous-réseau est grand : `/23` = 512 adresses, `/22` = 1024, `/16` = 65 536. Plus grand, plus petit : `/25` = 128, `/30` = 4.
- On rencontre aussi le **masque** `255.255.255.0`, qui dit la même chose que `/24` (macOS l’affiche en `0xffffff00`).

`192.168.1.20/24` se lit donc : « l’appareil `192.168.1.20`, dans le sous-réseau `192.168.1.0/24` ». Deux appareils ne se joignent directement que s’ils sont dans le même sous-réseau.

Les adresses **privées**, celles des réseaux locaux, sont dans `10.0.0.0/8`, `172.16.0.0/12` (de `172.16` à `172.31`) et `192.168.0.0/16`. Une box domestique distribue presque toujours du `192.168.x.0/24`.

La Détection accepte au plus **1024 adresses** au total (un `/22`, ou quatre `/24`) : au-delà, elle durerait trop longtemps.

## 2. Trouver son sous-réseau sur la machine Linux

Sur la machine ArgOS, `ip -4 addr` liste les **prises** (interfaces réseau) et leur adresse IPv4 :

```
$ ip -4 addr
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 ...
    inet 127.0.0.1/8 scope host lo
2: enp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
    inet 192.168.1.20/24 brd 192.168.1.255 scope global dynamic enp1s0
3: enp2s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
    inet 10.10.0.1/24 brd 10.10.0.255 scope global enp2s0
4: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 ...
    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0
```

- `lo` est la **boucle locale** : la machine qui se parle à elle-même. À ignorer.
- `docker0` (et les `br-…`, `veth…`) sont des **réseaux internes de Docker**, qui n’existent que dans la machine. À ignorer.
- `enp1s0`, `enp2s0` (ou `eth0`, `eno1`…) sont les **vraies prises Ethernet**. Le nom dépend de la carte réseau ; `wlan0` / `wlp…` serait le Wi-Fi.

Sur la ligne `inet`, l’adresse de la prise et la taille de son sous-réseau : `192.168.1.20/24` → sous-réseau `192.168.1.0/24`.

Pour savoir si un câble est branché : `ip link` affiche `state UP` sur une prise reliée, `NO-CARRIER` / `state DOWN` sur une prise sans câble (ou dont l’autre bout est éteint).

### Une seule prise

La machine, les caméras et les postes (ordinateurs, téléphones sur le Wi-Fi de la box) sont sur le **même** réseau : la prise de la machine porte le seul sous-réseau à chercher, par exemple `192.168.1.0/24`. C’est le plus simple, mais tout appareil du réseau (y compris un invité sur le Wi-Fi) peut joindre les caméras.

### Deux prises : réseau des caméras isolé

Installation recommandée ([sécurité](../securite.md#rejeu--injection-de-flux--comme-dans-les-films-)) : une prise vers la box (postes, internet), une autre vers un **switch réservé aux caméras**.

```
box ── enp1s0 (192.168.1.20/24) ── machine ArgOS ── enp2s0 (10.10.0.1/24) ── switch ── caméras
```

Dans l’exemple ci-dessus, les caméras sont sur `enp2s0` : le sous-réseau à chercher est `10.10.0.0/24`, pas celui de la box. Les caméras ne joignent ni la box ni internet ; seule la machine ArgOS les voit. C’est la prise `enp2s0` qu’il faudra choisir dans le script (§ 6).

## 3. Pourquoi l’API, dans Docker, ne voit pas les prises

ArgOS tourne dans des **conteneurs Docker** : la Détection part du conteneur `api`. Docker met ce conteneur sur un **réseau bridge** interne (une adresse du genre `172.18.0.5`), et fait sortir son trafic vers le réseau local en passant par la machine (**NAT**, comme une box pour les appareils de la maison).

Conséquences :

- `api` **joint** les adresses du réseau local : il peut appeler une caméra en `10.10.0.50`.
- Mais il ne **voit** pas les prises de la machine : depuis le conteneur, il n’existe ni `enp1s0` ni `enp2s0`, seulement son réseau Docker. Il ne peut donc pas deviner seul sur quel sous-réseau chercher.
- Il ne voit pas non plus les **adresses MAC** des appareils (l’identifiant matériel de chaque carte réseau) : elles restent de l’autre côté du NAT. Depuis la 0.4.2, en prod Linux, `api` rejoint en plus le réseau des caméras pour les lire (§ 9).

Mettre `api` directement sur le réseau de la machine (`network_mode: host`) réglerait la question, mais casserait le reste (noms des conteneurs, exposition des ports, comportement différent sous Docker Desktop) : choix écarté dans l’[ADR 0002](../adr/0002-detection-depuis-le-reseau-bridge.md).

D’où le **script** `scripts/cameras/configurer-detection.sh` (§ 6) : il tourne **sur la machine**, hors de Docker, là où les prises sont visibles. Il lit le sous-réseau de la prise des caméras et l’écrit dans `.env` (`ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX`), que Docker Compose passe à `api` au démarrage.

## 4. Ce que fait la Détection, et ce qu’elle ne fait pas

Un clic sur **Détecter des Caméras** (Administration, session connectée) lance, pendant une dizaine de secondes :

1. **Les cibles** : chaque adresse des sous-réseaux autorisés (sans la première ni la dernière, réservées), sur chaque port caméra (`ARGOS_DETECTION_CAMERAS_PORTS`, par défaut `554` et `8554`, les ports RTSP usuels). Les adresses des conteneurs d’ArgOS (`api`, le pont `mediamtx`) sont retirées d’avance.
2. **Connexion TCP** sur l’adresse et le port. Rien ne répond, ou refus : on passe à la suivante. Chaque essai est borné à 1,5 s ; 128 essais tournent en même temps. Un `/24` sur deux ports (508 essais) tient ainsi en moins de 10 s.
3. **Requête RTSP `OPTIONS`**, si la connexion est acceptée : la question la plus anodine du protocole des caméras (« quelles commandes acceptes-tu ? »), sans chemin de Flux ni identifiants. Si la réponse commence par une ligne de statut RTSP (`RTSP/1.0 200 OK`, mais aussi `401 Unauthorized` ou autre), l’hôte est un **Candidat**. Un port ouvert qui ne répond pas en RTSP (une imprimante, un serveur web) n’en est pas un.
4. **ArgOS lui-même est écarté** : la machine qui héberge ArgOS publie le pont, qui répond en RTSP comme une caméra. L’API demande à chaque Candidat, sur le port 8000, `GET /api/instance` ; celui qui renvoie le jeton de cette instance (tiré au hasard à chaque démarrage) est ArgOS, et disparaît de la liste.
5. **MAC de l’Appareil** : la connexion TCP vient de faire demander la MAC du Candidat (ARP, § 9) ; l’API la lit dans sa table de voisinage. Illisible (réseau routé, Mac de dev avec de vraies caméras) : pas de MAC, « — » dans l’UI.
6. **Rapprochement avec les Caméras du Site** : d’abord par MAC, un Candidat dont la MAC est celle d’une Caméra (active ou désactivée) est son Appareil, même à une autre IP (§ 10) ; sinon, un Candidat dont l’adresse IP et le port sont ceux de l’URL RTSP d’une Caméra (un nom d’hôte dans l’URL est d’abord résolu en IP). Il est rangé dans **Déjà configurées (n)**, avec le nom de la Caméra, replié par défaut.

L’UI montre ensuite les sous-réseaux couverts et les nouveaux Candidats (IP, port, MAC), triés par adresse. **Filtrer par MAC**, au-dessus de la liste, retrouve la caméra qu’on a dans la main : on tape la MAC telle qu’écrite sur son étiquette (`AA-BB-CC-DD-EE-FF`, `aabb.ccdd.eeff`, majuscules ou non), entière ou en partie. L’API renvoie en plus, pour le diagnostic, le statut RTSP reçu et l’en-tête `Server` annoncé (souvent la marque ou le firmware), et les écrit dans ses journaux :

```bash
docker compose logs api | grep Détection
# INFO:     Détection : Candidat 10.10.0.50:554 RTSP 200 Server Hikvision-Webs
# INFO:     Détection : bilan sous-réseaux 10.10.0.0/24, ports 554,8554, 6.2 s, 3 Candidat(s)
```

Une seule Détection tourne à la fois : une seconde, lancée pendant la première, est refusée avec un message.

**Ce qu’elle ne fait pas** :

- **Rien n’est ajouté ni stocké** : un Candidat n’est pas une Caméra, et disparaît au rechargement de la page. Pour en faire une Caméra : **Ajouter** sur sa ligne (ou **Ajouter par adresse IP** pour un appareil non détecté), voir [Ajouter une Caméra](ajouter-une-camera.md).
- **Aucun identifiant n’est envoyé**, et la Détection ne dit pas si une caméra est protégée : `OPTIONS` répond en général sans mot de passe. Une caméra protégée apparaît donc comme les autres ; le mot de passe est demandé à l’ajout.
- **Pas de Détection automatique** : une Caméra qui passe `offline` ne fait jamais balayer le réseau. Pour retrouver une caméra qui a changé d’IP, l’Administrateur relance la Détection (§ 10).
- **Pas d’ONVIF, de mDNS ni de lecture du switch** : seul compte ce qui accepte une connexion RTSP depuis la machine ArgOS, sur les ports sondés.
- **Rien hors des sous-réseaux autorisés** : une caméra restée sur une autre plage d’adresses est invisible (§ 5).
- **Pas d’IPv6.**

## 5. Le piège : qui donne une adresse aux caméras ?

Une caméra qu’on branche ne choisit pas seule une adresse utile. Trois cas :

- **Un serveur DHCP répond** : sur un réseau avec box, c’est elle. Elle distribue une adresse de son sous-réseau à tout appareil qui la demande ; la caméra, réglée en DHCP, prend par exemple `192.168.1.57`. La Détection la trouve, à condition de chercher sur ce sous-réseau. L’adresse peut changer après une coupure (bail DHCP) ; une **réservation** dans la box (même adresse pour cette caméra) l’évite.
- **Aucun DHCP, caméra en adresse fixe d’usine** : beaucoup de caméras sortent d’usine avec une adresse fixe, par exemple **Hikvision `192.168.1.64`**, **Dahua `192.168.1.108`** (voir la notice du modèle). Si le réseau des caméras est en `10.10.0.0/24`, une caméra en `192.168.1.64` n’en fait pas partie : la machine ArgOS ne la joint pas, la Détection ne la voit pas, même branchée sur le bon switch. Et deux caméras de la même marque auraient la même adresse.
- **Aucun DHCP, caméra en DHCP** : elle n’obtient rien et se donne souvent une adresse **`169.254.x.x`** (« lien local », auto-attribuée). Ces adresses ne servent qu’à dépanner : le script les écarte, et la Détection ne les cherche pas.

Le réseau isolé des caméras (deux prises, § 2) est le plus exposé : derrière un simple switch, **personne ne fait DHCP**. Si la prise de la machine elle-même n’a qu’une adresse `169.254.x.x`, ou aucune, le script prévient (« pas d’adresse IPv4 privée ») et la Détection n’est pas configurée.

Solutions, de la plus durable à la plus ponctuelle :

1. **Un serveur DHCP sur le réseau des caméras** : un routeur dédié, ou la machine ArgOS elle-même (par exemple `dnsmasq` sur `enp2s0`, avec une adresse fixe pour la machine). ArgOS ne l’installe pas : c’est un réglage de la machine.
2. **Régler chaque caméra en adresse fixe** dans le sous-réseau des caméras, depuis son interface web ou l’outil du fabricant (SADP chez Hikvision, ConfigTool chez Dahua), en notant les adresses données.
3. **Rejoindre temporairement le sous-réseau d’usine** pour atteindre une caméra neuve et la reconfigurer : `sudo ip addr add 192.168.1.2/24 dev enp2s0`, puis `sudo ip addr del 192.168.1.2/24 dev enp2s0` une fois fini. Tant que cette adresse existe, le script la voit aussi et ajoute `192.168.1.0/24` aux sous-réseaux de la Détection au prochain lancement.

## 6. Le script de configuration

`scripts/cameras/configurer-detection.sh`, lancé **sur la machine ArgOS**, depuis la racine du dépôt (Linux : lit `ip` ; macOS : `ifconfig`) :

```bash
scripts/cameras/configurer-detection.sh
docker compose up -d --wait   # recrée api avec le nouveau réglage
```

Il :

1. liste les prises qui ont une **adresse IPv4 privée**, en écartant la boucle locale, les réseaux Docker (`docker0`, `br-…`, `veth…`) et les `169.254.x.x` ;
2. **au premier lancement**, demande quelle(s) prise(s) relient les caméras (numéros séparés par des espaces), sauf s’il n’y en a qu’une, prise d’office, et retient la réponse dans `.env` : `ARGOS_DETECTION_CAMERAS_INTERFACES=enp2s0` ;
3. **à chaque lancement**, relit l’adresse actuelle des prises retenues, en déduit leur(s) sous-réseau(x) et les écrit dans `.env` : `ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX=10.10.0.0/24`. La Détection suit ainsi un changement d’adresse sans rien reconfigurer ;
4. prévient si une prise retenue n’a pas d’adresse (câble débranché, pas de DHCP, § 5) : le réglage est vidé et la Détection affiche « non configurée » ;
5. refuse une plage de plus de 1024 adresses (par exemple une prise en `/16`), en expliquant pourquoi : réglage vidé, sortie en erreur ;
6. **sur Linux seulement**, prépare le réseau des caméras (§ 9) : au premier lancement en terminal, propose une IP libre pour ArgOS sur la prise des caméras et la retient (`ARGOS_RESEAU_CAMERAS_IP`), puis ajoute `compose.reseau-cameras.yaml` à `COMPOSE_FILE` dans `.env`. Sous macOS, rien.

Sans terminal (démarrage automatique, § 7), il ne pose aucune question : il garde la prise et l’IP d’ArgOS retenues, ou, s’il y a plusieurs prises et aucune retenue, laisse la Détection non configurée en le disant ; sans IP retenue, le réseau des caméras n’est pas activé (pas de MAC pour les vraies caméras).

**Changer de prise** : vider `ARGOS_DETECTION_CAMERAS_INTERFACES=` dans `.env`, puis relancer le script dans un terminal.

**Ports sondés** : `ARGOS_DETECTION_CAMERAS_PORTS=554,8554` par défaut, à compléter dans `.env` pour un modèle qui sert le RTSP sur un autre port (ex. `554,8554,10554`). Le script n’y touche pas.

### Repli : à la main dans `.env`

Sans le script, écrire les sous-réseaux soi-même, en notation CIDR, séparés par des virgules, 1024 adresses au plus en tout :

```bash
ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX=10.10.0.0/24
```

puis `docker compose up -d --wait`. Le script **réécrit** cette valeur à chaque lancement : pour garder une valeur écrite à la main, ne plus le lancer (ni par le service du § 7). Une notation incorrecte ou une plage trop grande ne bloque pas ArgOS : seule la Détection est indisponible, et l’Administration affiche la raison.

## 7. Démarrage automatique de la machine Linux

Le sous-réseau doit être relu **après chaque redémarrage**, avant qu’ArgOS ne démarre : sinon `api` garde celui du dernier lancement. Docker relance bien les conteneurs tout seul (`restart: unless-stopped`), mais avec leur ancien réglage ; `docker compose up -d` les recrée quand `.env` a changé.

Exemple de service **systemd** (à adapter, rien n’est installé par ArgOS) : dépôt dans `/opt/argos`, compte `argos` propriétaire du dépôt et membre du groupe `docker` (lancé en `root`, le script rendrait `.env` illisible pour ce compte). La prise des caméras doit avoir été choisie une fois en terminal (§ 6).

```ini
# /etc/systemd/system/argos.service
[Unit]
Description=ArgOS : sous-réseaux de la Détection, puis la stack
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=argos
WorkingDirectory=/opt/argos
# « - » : un échec du script (plage trop grande) n'empêche pas ArgOS de démarrer.
ExecStartPre=-/opt/argos/scripts/cameras/configurer-detection.sh
ExecStart=/usr/bin/docker compose up -d --wait
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now argos.service
journalctl -u argos.service   # ce qu'a dit le script au dernier démarrage
```

`docker compose` lit `COMPOSE_FILE` dans `.env` : une fois le réseau des caméras activé par le script, `ExecStart` le monte sans rien changer au service. `network-online.target` attend que le réseau soit prêt (avec NetworkManager ou systemd-networkd, leur service `…-wait-online` doit être activé) : sinon la prise des caméras peut ne pas encore avoir son adresse DHCP quand le script la lit. Sans `compose.simulation.yaml` : c’est la stack de prod.

## 8. Le cas du dev

- **Sur Mac**, `lancer-argos.command` appelle le script (avec `ifconfig`) avant de démarrer la stack. La prise est en général `en0` (Wi-Fi ou Ethernet), sur le réseau de la box, par exemple `192.168.1.0/24`.
- La stack de dev ajoute **`compose.simulation.yaml`** : les trois Caméras simulées (`camera-simulee-1` à `-3`, RTSP sur le port 554, `-2` avec identifiants) vivent sur le réseau Compose `cameras-simulees`, en `172.30.0.0/24`, que `api` rejoint. Chacune y a une IP et une MAC fixes (`172.30.0.11` à `.13`, `02:a6:05:00:00:01` à `:03`) : `api` est leur voisin direct, il lit leurs MAC sans macvlan (§ 9). Ce fichier **ajoute** lui-même `172.30.0.0/24` aux sous-réseaux venus de `.env` : le script n’en sait rien, et la prod (`compose.yaml` seul) n’en garde aucune trace.
- La Détection balaie donc **aussi le réseau de la box** : tout appareil RTSP de la maison (une vraie caméra, un NAS, un décodeur) apparaît comme Candidat. C’est attendu. Le Mac lui-même, qui publie le pont sur `8554`, est reconnu et écarté (§ 4).
- Sans prise privée (Mac hors réseau), le script laisse le réglage vide : la Détection ne cherche alors que dans `172.30.0.0/24` et trouve les trois Caméras simulées.
- Sous Docker Desktop, `api` sort vers le réseau de la box par le NAT du Mac, comme sous Linux (§ 3). macvlan n’y existe pas : les vraies caméras vues depuis un Mac n’ont pas de MAC, et gardent le comportement de la 0.4.1 (§ 10). Lancer la stack à la main : README, [Protocole de lancement](../../README.md#protocole-de-lancement).

## 9. Reconnaître un Appareil : MAC, ARP, réseau des caméras

### L’adresse MAC

Une adresse IP se prête et se reprend : une caméra en DHCP peut recevoir une autre IP après une coupure ou à la fin de son bail (§ 5). Ce qui ne change pas, c’est l’**adresse MAC** de sa carte réseau : six octets gravés en usine, imprimés sur l’étiquette de la caméra, par exemple `AC-CC-8E-12-34-56`. Chaque fabricant l’écrit à sa façon (`AC:CC:8E:…`, `accc.8e12.3456`) ; ArgOS l’affiche toujours au même format : `ac:cc:8e:12:34:56`.

ArgOS appelle **Appareil** le matériel reconnu par sa MAC, et **Caméra** chaque Flux d’un Appareil. Une caméra ordinaire est un Appareil à une seule Caméra ; un enregistreur ou un encodeur multi-voies est un Appareil à plusieurs Caméras (§ 10).

### L’ARP : comment une machine apprend une MAC

Sur un même sous-réseau, les appareils ne s’échangent pas les paquets par IP, mais par MAC. Avant de parler à `10.10.0.50`, la machine crie sur le réseau « qui a `10.10.0.50` ? » : c’est une requête **ARP**. La caméra répond avec sa MAC, que la machine garde quelques minutes dans sa **table de voisinage** (`ip neigh` sur Linux).

Deux conséquences :

- On ne lit une MAC **qu’après avoir parlé** à l’IP : ArgOS lit la table juste après chaque sonde réussie (Détection, essai d’ajout, surveillance de l’état), quand la connexion vient de la remplir.
- On ne voit que les MAC des **voisins directs**. Derrière un routeur, la table donne la MAC du routeur pour toute adresse lointaine : inutile. ArgOS ne lit donc aucune MAC sur un réseau routé.

### Pourquoi l’API ne la voyait pas

Derrière le NAT de Docker (§ 3), c’est la **machine hôte** qui parle aux caméras, donc elle qui fait l’ARP et garde les MAC. Le conteneur `api`, lui, n’a pour voisin que le pont Docker : sa table de voisinage ne contient aucune caméra.

### macvlan : l’API sur le réseau des caméras

Depuis la 0.4.2, en **prod Linux**, `api` rejoint directement le réseau des caméras par une interface **macvlan** : une carte réseau virtuelle, avec sa propre MAC et sa propre IP, branchée sur la prise des caméras comme un appareil de plus sur le switch. `api` parle alors aux caméras sans NAT, fait lui-même l’ARP, et lit leurs MAC dans sa propre table. Il garde le réseau bridge pour le reste (noms des conteneurs, ports publiés, route par défaut). Pourquoi ce choix plutôt que la table ARP de l’hôte : [ADR 0003](../adr/0003-macvlan-sur-la-prise-des-cameras.md).

```
box ── enp1s0 (192.168.1.20) ── machine ArgOS ── enp2s0 (10.10.0.1) ── switch ── caméras
                                     │                  │
                          api : bridge Docker     api : macvlan 10.10.0.254
                          (UI, NAT, ports)        (sonde des caméras, ARP)
```

Ce réseau est une **sortie** : `api` y parle aux caméras, mais refuse toute requête qui y arrive (une caméra compromise ne joint pas l’API, voir [sécurité](../securite.md#réseau-des-caméras--une-sortie-seulement)).

### L’IP d’ArgOS sur le réseau des caméras

L’interface macvlan a besoin d’une IP du sous-réseau des caméras, **fixe**, et que personne d’autre n’utilise. Le script (§ 6) s’en charge au premier lancement en terminal :

1. il part du **haut** du sous-réseau (`10.10.0.254` pour un `/24`), loin des adresses que distribuent en général les serveurs DHCP, et propose la première adresse qui ne répond pas en ARP et n’est pas une adresse de la machine ;
2. on accepte (Entrée) ou on tape une autre adresse ; une adresse hors du sous-réseau, ou qui répond déjà en ARP, est refusée ;
3. il la retient dans `.env` (`ARGOS_RESEAU_CAMERAS_IP`), avec la prise et son sous-réseau (`ARGOS_RESEAU_CAMERAS_PRISE`, `ARGOS_RESEAU_CAMERAS_SOUS_RESEAU`), et ajoute `compose.reseau-cameras.yaml` à `COMPOSE_FILE`.

**À vérifier soi-même** : l’adresse doit être **hors de la plage DHCP** du réseau des caméras. Le script sait seulement qu’elle est libre maintenant ; si un serveur DHCP la donne plus tard à une caméra, les deux se gênent. Avec un DHCP sur ce réseau (box, routeur, `dnsmasq`), réduire sa plage ou y réserver l’adresse d’ArgOS.

À chaque lancement, le script revérifie l’IP retenue : sortie du sous-réseau de la prise (adresse de la prise changée), ou occupée par un autre appareil (répond en ARP), il **avertit** et désactive le réseau des caméras (retiré de `COMPOSE_FILE`) jusqu’à ce qu’on en choisisse une autre en terminal. ArgOS démarre quand même, sans MAC pour les vraies caméras.

Limites :

- **Une seule prise** : le réseau des caméras se monte sur la première prise retenue. Les caméras des autres prises sont détectées, mais sans MAC (le script le dit).
- La machine hôte elle-même ne joint pas l’IP macvlan d’`api` (propriété de macvlan sous Linux) : sans effet sur ArgOS, qui n’est servi que par le bridge.
- **Jamais sous macOS** : Docker Desktop ne gère pas macvlan. Sur un Mac, les vraies caméras restent sans MAC (§ 8).

Changer l’IP d’ArgOS : vider `ARGOS_RESEAU_CAMERAS_IP=` dans `.env`, relancer le script dans un terminal, puis `docker compose up -d --wait`.

## 10. Quand une caméra change d’IP

### Suivi à la Détection

ArgOS retient la MAC de l’Appareil de chaque Caméra dès qu’il la voit (à l’ajout, à la Détection, ou par la sonde). Quand une caméra a pris une autre IP, sa Caméra passe `offline` : rien n’est plus diffusé à son ancienne adresse. ArgOS ne la cherche pas de lui-même (§ 4) : l’Administrateur relance **Détecter des Caméras**.

La Détection trouve un Candidat dont la MAC est celle d’une Caméra du Site, à une autre IP. ArgOS :

1. remplace l’**hôte** de l’URL RTSP de toutes les Caméras de cet Appareil par la nouvelle IP : port, chemin et identifiants sont gardés (`rtsp://admin:***@10.10.0.57/Streaming/Channels/101` devient `rtsp://admin:***@10.10.0.61/Streaming/Channels/101`). Les Caméras désactivées suivent aussi, pour être justes à leur réactivation ;
2. range le Candidat dans **Déjà configurées**, avec la mention **adresse mise à jour (10.10.0.57 → 10.10.0.61)** ;
3. remet la Caméra à `unknown` ; le pont la relaie à sa nouvelle adresse, la sonde la repasse `online`, et elle revient dans le Live, sans autre action.

Toutes les mises à jour d’une Détection s’écrivent ensemble : deux caméras qui ont **échangé** leurs IP sont toutes deux corrigées.

**Conflit** : si la nouvelle URL est déjà celle d’une autre Caméra, sans MAC, qui ne bouge pas, ArgOS ne modifie pas la Caméra de l’Appareil, et le Candidat l’affiche : **adresse non mise à jour : URL déjà prise par <nom>**. À corriger à la main (**Modifier**), puis relancer la Détection.

### « Autre appareil à cette adresse »

Pire qu’une caméra qui part : un **autre** appareil qui reprend son IP (une autre caméra a reçu ce bail). Il répond peut-être en RTSP au même chemin, et la Caméra semblerait `online` avec l’image d’une autre caméra.

La sonde de l’état vérifie donc aussi la MAC : quand le Flux d’une Caméra répond, mais depuis une **autre MAC** que celle de son Appareil, la Caméra passe `offline`, l’Administration affiche **autre appareil à cette adresse** à côté de l’état, et le pont cesse de la relayer : son Flux disparaît du Live. Dès que la bonne MAC est revue à cette adresse, la raison s’efface et le relais reprend. Pour retrouver la caméra à sa nouvelle IP : relancer une Détection.

### Caméras sans MAC

Une Caméra peut ne pas avoir de MAC :

- elle a été **ajoutée avant la 0.4.2** : elle reçoit sa MAC d’elle-même, la première fois qu’une Détection ou la sonde voit son Appareil à son IP, sans migration manuelle ;
- sa MAC est **illisible** : caméra derrière un routeur (réseau routé), réseau des caméras non activé, ou **Mac de dev** avec de vraies caméras (pas de macvlan sous Docker Desktop).

Sans MAC, la Caméra garde le comportement de la 0.4.1 : l’UI affiche **—**, elle est rapprochée des Candidats par IP et port, et si elle change d’IP, elle reste `offline` jusqu’à ce qu’on corrige son URL (**Modifier**).

### Un Appareil à plusieurs Caméras

Un enregistreur (NVR), un encodeur multi-voies ou une caméra à plusieurs objectifs porte **plusieurs Flux sous une seule MAC**, un par chemin RTSP. ArgOS le tolère depuis la 0.4.2 :

- **à l’ajout**, un Flux déjà configuré sur le même Appareil (même MAC, même chemin, même si l’IP a changé) est refusé : **Déjà configurée : <nom>**. Un autre chemin du même Appareil est permis, avec l’avertissement **Cet appareil porte déjà la Caméra <nom>** ([Ajouter une Caméra](ajouter-une-camera.md#1-le-déroulé)) ;
- **à la Détection**, toutes ses Caméras sont mises à jour ensemble quand son IP change ; le Candidat est rangé sous la plus ancienne (au même port de préférence).

**Reste à étudier** sur du vrai matériel ([feuille de route](../dev/feuille-de-route/feuille-de-route-dev.md#un-appareil-plusieurs-caméras)) : comment chaque voie expose son chemin RTSP selon les marques, proposer à l’ajout toutes les voies d’un Appareil plutôt que la première trouvée, et regrouper les Caméras d’un même Appareil dans l’Administration.
