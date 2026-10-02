# Réseau du Site et Détection des Caméras

Comprendre, et pouvoir expliquer, comment les Caméras sont reliées à la machine qui héberge ArgOS, et ce que fait le bouton **Détecter des Caméras** de l’Administration. Écrit pour quelqu’un qui n’est pas spécialiste du réseau.

Pour aller plus loin : [ADR 0002](../adr/0002-detection-depuis-le-reseau-bridge.md) (pourquoi les sous-réseaux sont déclarés), [sécurité](../securite.md#détection--argos-agit-sur-le-réseau) (ce que la Détection envoie), [schéma des Flux](../dev/schema-flux.md).

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
- Il ne voit pas non plus les **adresses MAC** des appareils (l’identifiant matériel de chaque carte réseau) : elles restent de l’autre côté du NAT.

Mettre `api` directement sur le réseau de la machine (`network_mode: host`) réglerait la question, mais casserait le reste (noms des conteneurs, exposition des ports, comportement différent sous Docker Desktop) : choix écarté dans l’[ADR 0002](../adr/0002-detection-depuis-le-reseau-bridge.md).

D’où le **script** `scripts/cameras/configurer-detection.sh` (§ 6) : il tourne **sur la machine**, hors de Docker, là où les prises sont visibles. Il lit le sous-réseau de la prise des caméras et l’écrit dans `.env` (`ARGOS_DETECTION_CAMERAS_SOUS_RESEAUX`), que Docker Compose passe à `api` au démarrage.

## 4. Ce que fait la Détection, et ce qu’elle ne fait pas

Un clic sur **Détecter des Caméras** (Administration, session connectée) lance, pendant une dizaine de secondes :

1. **Les cibles** : chaque adresse des sous-réseaux autorisés (sans la première ni la dernière, réservées), sur chaque port caméra (`ARGOS_DETECTION_CAMERAS_PORTS`, par défaut `554` et `8554`, les ports RTSP usuels). Les adresses des conteneurs d’ArgOS (`api`, le pont `mediamtx`) sont retirées d’avance.
2. **Connexion TCP** sur l’adresse et le port. Rien ne répond, ou refus : on passe à la suivante. Chaque essai est borné à 1,5 s ; 128 essais tournent en même temps. Un `/24` sur deux ports (508 essais) tient ainsi en moins de 10 s.
3. **Requête RTSP `OPTIONS`**, si la connexion est acceptée : la question la plus anodine du protocole des caméras (« quelles commandes acceptes-tu ? »), sans chemin de Flux ni identifiants. Si la réponse commence par une ligne de statut RTSP (`RTSP/1.0 200 OK`, mais aussi `401 Unauthorized` ou autre), l’hôte est un **Candidat**. Un port ouvert qui ne répond pas en RTSP (une imprimante, un serveur web) n’en est pas un.
4. **ArgOS lui-même est écarté** : la machine qui héberge ArgOS publie le pont, qui répond en RTSP comme une caméra. L’API demande à chaque Candidat, sur le port 8000, `GET /api/instance` ; celui qui renvoie le jeton de cette instance (tiré au hasard à chaque démarrage) est ArgOS, et disparaît de la liste.
5. **Rapprochement avec les Caméras du Site** : un Candidat dont l’adresse IP et le port sont ceux de l’URL RTSP d’une Caméra (active ou désactivée ; un nom d’hôte dans l’URL est d’abord résolu en IP) est rangé dans **Déjà configurées (n)**, avec le nom de la Caméra, replié par défaut.

L’UI montre ensuite les sous-réseaux couverts et les nouveaux Candidats (IP, port), triés par adresse. L’API renvoie en plus, pour le diagnostic, le statut RTSP reçu et l’en-tête `Server` annoncé (souvent la marque ou le firmware), et les écrit dans ses journaux :

```bash
docker compose logs api | grep Détection
# INFO:     Détection : Candidat 10.10.0.50:554 RTSP 200 Server Hikvision-Webs
# INFO:     Détection : bilan sous-réseaux 10.10.0.0/24, ports 554,8554, 6.2 s, 3 Candidat(s)
```

Une seule Détection tourne à la fois : une seconde, lancée pendant la première, est refusée avec un message.

**Ce qu’elle ne fait pas** :

- **Rien n’est ajouté ni stocké** : un Candidat n’est pas une Caméra, et disparaît au rechargement de la page. L’ajout depuis un Candidat arrive en 0.4.1.
- **Aucun identifiant n’est envoyé**, et la Détection ne dit pas si une caméra est protégée : `OPTIONS` répond en général sans mot de passe. Une caméra protégée apparaît donc comme les autres.
- **Pas d’adresse MAC** (invisible depuis `api`, § 3) : si une caméra change d’IP, rien ne la reconnaît. Identité par MAC : 0.4.2.
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
5. refuse une plage de plus de 1024 adresses (par exemple une prise en `/16`), en expliquant pourquoi : réglage vidé, sortie en erreur.

Sans terminal (démarrage automatique, § 7), il ne pose aucune question : il garde la prise retenue, ou, s’il y a plusieurs prises et aucune retenue, laisse la Détection non configurée en le disant.

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

`network-online.target` attend que le réseau soit prêt (avec NetworkManager ou systemd-networkd, leur service `…-wait-online` doit être activé) : sinon la prise des caméras peut ne pas encore avoir son adresse DHCP quand le script la lit. Sans `compose.simulation.yaml` : c’est la stack de prod.

## 8. Le cas du dev

- **Sur Mac**, `lancer-argos.command` appelle le script (avec `ifconfig`) avant de démarrer la stack. La prise est en général `en0` (Wi-Fi ou Ethernet), sur le réseau de la box, par exemple `192.168.1.0/24`.
- La stack de dev ajoute **`compose.simulation.yaml`** : les trois Caméras simulées (`camera-simulee-1` à `-3`, RTSP sur le port 554, `-2` avec identifiants) vivent sur le réseau Compose `cameras-simulees`, en `172.30.0.0/24`, que `api` rejoint. Ce fichier **ajoute** lui-même `172.30.0.0/24` aux sous-réseaux venus de `.env` : le script n’en sait rien, et la prod (`compose.yaml` seul) n’en garde aucune trace.
- La Détection balaie donc **aussi le réseau de la box** : tout appareil RTSP de la maison (une vraie caméra, un NAS, un décodeur) apparaît comme Candidat. C’est attendu. Le Mac lui-même, qui publie le pont sur `8554`, est reconnu et écarté (§ 4).
- Sans prise privée (Mac hors réseau), le script laisse le réglage vide : la Détection ne cherche alors que dans `172.30.0.0/24` et trouve les trois Caméras simulées.
- Sous Docker Desktop, `api` sort vers le réseau de la box par le NAT du Mac, comme sous Linux (§ 3). Lancer la stack à la main : README, [Protocole de lancement](../../README.md#protocole-de-lancement).
