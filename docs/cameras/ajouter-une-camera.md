# Ajouter une Caméra

Comprendre ce que fait ArgOS quand l’Administrateur clique sur **Ajouter**, et quoi faire quand ça bloque. Depuis la 0.4.1, l’Administrateur n’écrit plus jamais d’URL RTSP pour ajouter une Caméra : ArgOS cherche seul le Flux, demande un mot de passe ou un chemin seulement s’il en a besoin, et montre l’image avant l’ajout.

Pour aller plus loin : [Réseau du Site et Détection des Caméras](reseau-et-detection.md) (d’où viennent les Candidats), [Reconnaître un Appareil par sa MAC](reseau-et-detection.md#9-reconnaître-un-appareil--mac-arp-réseau-des-caméras) (MAC, changement d’IP, Appareil à plusieurs Caméras), [sécurité](../securite.md#ajout-dune-caméra--argos-essaie-un-flux) (garde-fous de l’essai, mots de passe), [schéma des Flux](../dev/schema-flux.md), [HLS pour les Flux H.265](../adr/0004-hls-pour-les-flux-h265.md) (pourquoi deux transports).

## 1. Le déroulé

Dans l’**Administration**, section Détection :

1. **Ajouter** sur un nouveau Candidat (ou **Ajouter par adresse IP**, § 6). Un panneau s’ouvre sous la ligne, sans quitter la liste.
2. **Recherche du Flux…** : ArgOS essaie les chemins courants des caméras (§ 2). Quelques secondes.
3. Selon la réponse de la caméra :
   - Flux trouvé → **Aperçu** (§ 5) ;
   - Flux trouvé, mais déjà configuré sur le même appareil (même MAC, même chemin, même si l’IP a changé) → **Déjà configurée : <nom>**, sans Aperçu ;
   - **Cette caméra demande un mot de passe.** → identifiant et mot de passe (§ 3) ;
   - **Flux introuvable.** → chemin RTSP (§ 4) ;
   - **Aucune caméra ne répond à cette adresse.** → rien à faire depuis ArgOS : la caméra est éteinte, a changé d’adresse, ou ne parle pas RTSP sur ce port.
4. Sous l’Aperçu : **Nom** (obligatoire), **Emplacement** (facultatif), puis **Ajouter la Caméra**. Elle est créée active, apparaît dans la liste des Caméras et dans le Live, et le Candidat passe dans **Déjà configurées**, sans relancer de Détection. Si l’appareil porte déjà une autre Caméra (même MAC, autre chemin : enregistreur, encodeur multi-voies), l’Aperçu avertit **Cet appareil porte déjà la Caméra <nom>** ; l’ajout reste permis.

**Annuler** est offert à chaque étape : rien n’est créé, et l’Aperçu est retiré. Un nom déjà pris est refusé avec le message habituel ; l’Aperçu reste ouvert pour corriger.

## 2. Les chemins courants

Une caméra IP sert son Flux à une adresse de la forme `rtsp://ip:port/chemin`. Le **chemin** dépend de la marque, parfois du modèle : `/Streaming/Channels/101` chez Hikvision, `/cam/realmonitor?channel=1&subtype=0` chez Dahua, `/h264Preview_01_main` chez Reolink… C’est ce que l’Administrateur ne connaît pas, et qu’ArgOS cherche à sa place.

1. **`OPTIONS`** : la même question anodine que la Détection. Sans réponse RTSP, l’essai s’arrête : « Aucune caméra ne répond à cette adresse ». La réponse porte souvent un en-tête `Server` qui nomme la marque.
2. **`DESCRIBE` sur chaque chemin courant**, dans l’ordre, jusqu’au premier qui répond `200` (« ce Flux existe, voici sa description »). Les chemins de la marque reconnue dans `Server` passent en tête ; pour chaque marque, le **Flux principal** (meilleure qualité) avant le flux secondaire.
3. **Confirmation par la sonde** : ArgOS ouvre le Flux et attend au moins un paquet vidéo, comme pour l’état `online` d’une Caméra. Une caméra qui décrit un Flux sans rien émettre n’est pas retenue.

La liste est dans `api/argos_api/essai.py` (`CHEMINS_COURANTS`) : Hikvision, Dahua, Reolink, Uniview, Axis, puis quelques chemins génériques. Elle ne contient rien de propre aux Caméras simulées.

## 3. Le mot de passe, avant le chemin

La plupart des caméras protégées répondent `401 Unauthorized` à **n’importe quel** `DESCRIBE` sans identifiants, avant même de regarder le chemin : elles ne disent pas si le chemin existe. Essayer les autres chemins sans mot de passe ne sert donc à rien. Dès le premier `401`, ArgOS s’arrête et affiche **Cette caméra demande un mot de passe.**

- L’identifiant est prérempli avec `admin` (le plus courant), modifiable.
- **Valider** relance les chemins courants avec ces identifiants.
- Un nouveau `401` → **Identifiant ou mot de passe refusé par la caméra.** On corrige et on valide à nouveau.

**Un seul essai d’identifiants par clic** : ArgOS s’arrête au premier refus, sans essayer d’autre chemin, sans réessai automatique, sans tester de mots de passe par défaut. Beaucoup de caméras se verrouillent (ou bloquent l’adresse d’ArgOS) après quelques échecs.

Le mot de passe saisi ne revient jamais dans le navigateur : l’API compose l’URL `rtsp://identifiant:motdepasse@ip:port/chemin` (caractères spéciaux encodés), la garde côté serveur pendant l’essai, et crée la Caméra à partir d’elle. Ensuite, il est masqué (`***`) partout, comme pour toute Caméra.

## 4. Le repli par chemin

Aucun chemin courant ne répond `200` : **Flux introuvable.**, et un champ **Chemin RTSP**. C’est le cas d’une caméra exotique : son chemin est dans sa notice ou sur le site du fabricant. On le saisit avec ou sans `/` au début ; **Valider** n’essaie que lui, **avec les identifiants déjà donnés** (pas besoin de les ressaisir).

## 5. L’Aperçu

Dès que le Flux est trouvé, son **Aperçu** s’affiche dans le panneau : la vraie image de la caméra, pour vérifier que c’est la bonne avant de la nommer.

- Au-dessus, la **MAC de l’Appareil** (`aa:bb:cc:dd:ee:ff`, ou « — » si illisible) : à comparer à l’étiquette de la caméra. La Caméra ajoutée la garde ([pourquoi](reseau-et-detection.md#10-quand-une-caméra-change-dip)).
- C’est un chemin éphémère du pont MediaMTX, `apercu-<jeton aléatoire>`, lu comme le Live : en WebRTC, ou en HLS si le Flux est en H.265 (ci-dessous). Il n’apparaît **jamais** dans le Live, qui ne montre que des Caméras.
- **Un seul à la fois** pour le Site : ouvrir un autre Candidat ferme le précédent.
- Retiré à l’ajout, à l’annulation, au lancement d’un autre essai, et de lui-même **2 minutes** après son dernier renouvellement (`ARGOS_APERCU_EXPIRATION_S`). Le panneau le renouvelle tant qu’il est ouvert : on peut prendre son temps pour le nommer. Onglet fermé sans **Annuler** : l’Aperçu expire seul. Au démarrage, l’API retire les `apercu-*` laissés par une instance précédente.

### Caméras H.265

Beaucoup de caméras récentes émettent par défaut en **H.265** (HEVC). ArgOS lit le codec dans la description du Flux, le retient sur la Caméra à l’ajout, puis la sonde le tient à jour (une caméra reconfigurée H.264 ↔ H.265 est suivie seule). L’Administration l’affiche à côté de l’état : « H.264 », « H.265 », « inconnu » si jamais lu.

**Le transport est choisi par le codec**, dans le Live comme dans l’Aperçu, sans rien régler ([ADR 0004](../adr/0004-hls-pour-les-flux-h265.md)) :

| Codec | Transport | Retard |
|---|---|---|
| H.264, autre ou inconnu | WebRTC (WHEP) | moins d’une seconde |
| H.265 | LL-HLS fMP4, port `8888` | **1 à 3 s**, démarrage un peu plus lent |

Le Flux H.265 n’est **pas réencodé** : le pont remballe les images telles quelles, et c’est le **navigateur** (souvent la puce vidéo de l’ordinateur) qui décode le HEVC. Tous ne le savent pas :

- **Safari** (Mac, iPhone, iPad) : le lit ;
- **Chrome** et **Edge** : le lisent si la machine a un **décodage matériel** HEVC (Mac M1 et suivants, PC Intel / AMD récents) ;
- **Firefox** : le plus souvent non.

Avant de lire, l’UI demande au navigateur s’il décode le HEVC. S’il ne le décode pas, ou échoue en lisant, la vidéo laisse place à **« Ce navigateur ne lit pas le H.265 »**, sans nouvelle tentative toutes les 5 s : réessayer n’y changerait rien. Ce n’est ni la caméra ni le réseau : ouvrir l’UI dans Safari, ou dans Chrome sur une machine récente. Une Caméra H.265 injoignable affiche, elle, **Flux indisponible** et retente comme les autres. Dans l’Aperçu, l’ajout reste permis dans les deux cas.

Sans navigateur qui décode le HEVC, deux remèdes :

- **Sur la caméra** (son interface web) : passer le flux principal en H.264, quand le modèle le permet. ArgOS suit le changement au passage suivant de la sonde.
- **Dans ArgOS, en 0.5.1** : réencodage H.265 → H.264 **à la demande**, seulement pendant qu’un tel navigateur regarde ([feuille de route](../dev/feuille-de-route-dev.md)).

Un codec **ni H.264 ni H.265** (MJPEG…) n’est toujours pas montré : le panneau le nomme (« Cette caméra émet en MJPEG, que le navigateur ne sait pas lire… ») ; l’ajout reste permis, la Caméra est sondée normalement, mais le Live ne l’affiche pas.

## 6. Ajouter par adresse IP

Pour un appareil que la Détection n’a pas trouvé (sous-réseau non déclaré, port exotique, Détection pas configurée) : **Ajouter par adresse IP**, dans la section Détection. IP, port (`554` par défaut), **Ajouter** : la suite est exactement le même parcours qu’un Candidat détecté.

Avant d’essayer, ArgOS refuse :

- une IP **déjà configurée** (même IP et même port qu’une Caméra du Site, désactivées comprises) : **Déjà configurée : <nom>**, sans ouvrir le parcours ;
- une IP **hors du réseau local** (seules `10.x`, `172.16-31.x` et `192.168.x` sont acceptées) : ArgOS ne sert pas à joindre internet ;
- une IP **d’ArgOS lui-même** (la machine qui publie le pont, ou un de ses conteneurs).

## 7. Les Caméras simulées

En dev, chacune des quatre Caméras simulées montre un parcours :

| Caméra simulée | Parcours |
|---|---|
| `camera-simulee-1` | Flux trouvé seul, chemin style Hikvision (`/Streaming/Channels/101`) |
| `camera-simulee-2` | **Cette caméra demande un mot de passe** : identifiant `admin`, mot de passe `argos-simulee` ; chemin style Dahua trouvé ensuite |
| `camera-simulee-3` | **Flux introuvable** : chemin RTSP `/flux` |
| `camera-simulee-4` | Flux trouvé seul, chemin style Hikvision, en **H.265** : Aperçu en HLS, ou « Ce navigateur ne lit pas le H.265 » (§ 5) |

## 8. Diagnostiquer

Chaque essai écrit une ligne dans les journaux de l’API, **sans identifiants ni URL complète** :

```bash
docker compose logs api | grep Essai
# INFO:     Essai : 172.30.0.12:554 issue identifiants_requis chemin None codec None
# INFO:     Essai : 172.30.0.12:554 issue flux_trouve chemin /cam/realmonitor?channel=1&subtype=0 codec H264
```

Issues possibles : `flux_trouve`, `identifiants_requis`, `identifiants_refuses`, `flux_introuvable`, `injoignable`.

Un essai à la fois : un second, lancé pendant la recherche, est refusé (« Un essai est déjà en cours »). L’essai est réservé à une session connectée.

## 9. Ce que l’ajout ne fait pas

- **Pas d’ONVIF** : ArgOS ne demande pas son chemin à la caméra, il essaie une liste. Pas de PTZ.
- **Pas de choix entre flux principal et secondaire** : le principal est pris quand il répond.
- **Pas d’ajout par MAC** : pour retrouver une caméra parmi les Candidats, **Filtrer par MAC** dans la liste ([Détection](reseau-et-detection.md#4-ce-que-fait-la-détection-et-ce-quelle-ne-fait-pas)), puis **Ajouter**.
- **Pas de MAC modifiable** : ArgOS la lit sur le réseau, l’Administrateur ne la saisit jamais. Une Caméra sans MAC (réseau routé, Mac de dev avec de vraies caméras) qui change d’IP reste `offline` jusqu’à ce qu’on corrige son URL (**Modifier**) ; avec sa MAC, une Détection la retrouve seule ([quand une caméra change d’IP](reseau-et-detection.md#10-quand-une-caméra-change-dip)).
- **Pas de réencodage** : un navigateur qui ne décode pas le HEVC ne montre pas les Caméras H.265 (§ 5) avant la 0.5.1. Pas de lecture des autres codecs (MJPEG…).
- **Modifier une Caméra** passe toujours par son URL RTSP : l’URL affichée est masquée, la laisser telle quelle conserve le mot de passe.
