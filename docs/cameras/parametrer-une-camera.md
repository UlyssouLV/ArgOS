# Paramétrer une Caméra : ONVIF

Comprendre ce qu’on peut régler sur une caméra IP (nom et heure incrustés, horloge, image, vidéo), et comment le faire quand son interface web est inutilisable. Écrit à partir d’une vraie caméra générique branchée sur un Site de dev, en octobre 2026. ArgOS **ne règle encore rien** sur les caméras : il lit leur Flux, sans jamais leur envoyer de réglage. Cette page prépare la version qui le fera (voir la [feuille de route](../dev/feuille-de-route-dev.md)).

Pour aller plus loin : [Ajouter une Caméra](ajouter-une-camera.md), [Réseau du Site et Détection des Caméras](reseau-et-detection.md), [sécurité](../securite.md).

## 1. Ce que la caméra incruste dans l’image

Le nom (`CAM01`) et la date qui défile, visibles dans le Live, ne viennent pas d’ArgOS : la caméra les **dessine elle-même dans l’image**, avant de l’encoder. C’est l’**OSD** (*on-screen display*, affichage à l’écran). ArgOS relaie le Flux sans réencodage : il ne peut ni les effacer ni les changer dans l’image. Le seul moyen est de **régler la caméra**.

## 2. L’interface web, souvent une impasse

Une caméra IP a presque toujours une page web de réglages, à son adresse (`http://192.168.1.103`). Sur beaucoup de caméras génériques, cette page exige un vieux module Windows (ActiveX) : un navigateur récent affiche « navigateur non supporté », ou télécharge un `.exe`. Rien à faire depuis un Mac.

Restent l’application mobile du fabricant (souvent XMEye ou iCSee pour ces caméras), qui passe en général par son **cloud** et invite à y lier la caméra (contraire à l’esprit d’ArgOS, et aux recommandations de la [page sécurité](../securite.md), § 1), et **ONVIF**.

## 3. ONVIF, le protocole de réglage commun

**ONVIF** est un standard que suivent la plupart des caméras IP, toutes marques confondues, pour se décrire et se laisser régler : identité, réseau, heure, profils vidéo, OSD, image, PTZ, événements. Ce sont des requêtes HTTP au format SOAP (XML), protégées par l’identifiant et le mot de passe de la caméra : **les mêmes que pour le Flux RTSP**.

- Chaque fonction est un **service** (appareil, média, image, PTZ, événements…) à sa propre adresse, que la caméra annonce.
- Les commandes `Get…` lisent, les commandes `Set…` modifient. Une lecture ne change rien.
- Une caméra peut annoncer une fonction sans la respecter vraiment : on vérifie en relisant après chaque réglage.

### Trouver le port ONVIF

Le service d’entrée est `http://<ip>:<port>/onvif/device_service`. Le port **varie selon le fabricant** : `80` chez beaucoup, **`8899`** sur les caméras XiongMai, `2000` ou `8000` ailleurs. Une page web qui répond `200` sur `/onvif/device_service` ne prouve rien : il faut une réponse SOAP. Demander l’heure ne demande aucun identifiant :

```bash
B='<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>'
for p in 80 8899 2000 8000 8080; do
  echo "$p: $(curl -s -m 3 -X POST -H 'Content-Type: application/soap+xml' -d "$B" http://192.168.1.103:$p/onvif/device_service | head -c 80)"
done
# 8899: <?xml version="1.0" encoding="UTF-8"?><s:Envelope ...   ← le bon port
```

### Lire la caméra

La bibliothèque Python `onvif-zeep`, dans un conteneur jetable (rien à installer sur le Mac), avec les identifiants de la caméra passés par l’environnement, jamais écrits dans un fichier :

```bash
docker run --rm -e IP=192.168.1.103 -e ID=admin -e MDP='…' python:3.12-slim sh -c '
pip install -q onvif-zeep >/dev/null 2>&1 && python -c "
import os; from onvif import ONVIFCamera
cam = ONVIFCamera(os.environ[\"IP\"], 8899, os.environ[\"ID\"], os.environ[\"MDP\"], \"/usr/local/lib/python3.12/site-packages/wsdl/\")
print(cam.devicemgmt.GetDeviceInformation())
media = cam.create_media_service()
source = media.GetProfiles()[0].VideoSourceConfiguration.token
print(media.GetOSDs({\"ConfigurationToken\": source}))
"'
```

Autres lectures utiles : `GetSystemDateAndTime`, `GetNTP`, `GetNetworkInterfaces`, `GetDNS` (service appareil) ; `GetProfiles`, `GetOSDOptions`, `GetVideoEncoderConfigurationOptions` (média) ; `GetImagingSettings`, `GetOptions` (service image).

## 4. Ce qu’a montré la caméra de dev

| | |
|---|---|
| Fabricant, modèle | `H264` (générique), `IPC_GK7201V200_G3H_S38` : puce Goke, firmware XiongMai (en-tête RTSP `Server: H264DVR 1.0`) |
| ONVIF | port `8899` ; services appareil, média (1 et 2), image, PTZ, événements, analyse |
| Réseau | IP fixe, passerelle de la box ; la **MAC** se lit par ONVIF (`GetNetworkInterfaces`), même là où ArgOS ne peut pas la lire par ARP (Mac de dev) |
| Comptes | un seul, `admin` (administrateur) |
| Flux | principal 2304×1296, secondaire 800×448, instantané JPEG 704×576 |

### Réglable par ONVIF

- **OSD** : deux incrustations. Le **nom** (texte libre, `CAM01`, en haut à gauche) et la **date et heure** (`yyyy-MM-dd HH:mm:ss`, en bas à gauche). On peut changer le texte, déplacer l’une ou l’autre (un coin ou une position libre), ou les retirer. Ni police, ni taille, ni couleur, ni autre format de date.
- **Horloge** : fuseau, serveur de temps (NTP), ou heure manuelle.
- **Image** : luminosité, contraste, saturation, netteté, compensation de contre-jour, WDR, exposition, balance des blancs, **filtre infrarouge** (jour, nuit, automatique).
- **Vidéo** : résolution (720p, 1080p, 2304×1296), jusqu’à 22 images par seconde, débit, qualité, intervalle entre images clés.
- **PTZ** et **événements** (détection de mouvement, probablement) : annoncés, à étudier ; ce modèle n’a sans doute pas de moteur.

### Ce qui cloche, réglé d’usine

- **Horloge au 31/12/1999** : le serveur de temps s’appelle simplement `NTP`, un nom qui ne mène nulle part, et le fuseau est celui de l’Australie (`AWST-8`). L’heure incrustée est fausse, et le serait dans tout enregistrement. Remède : fuseau de Paris (`CET-1CEST,M3.5.0,M10.5.0/3`) et un vrai serveur de temps (la box, ou `pool.ntp.org`).
- **DNS chinois** (`114.114.114.114`) : la caméra cherche à joindre internet, comme beaucoup de caméras génériques. Bloquer son accès à internet dans la box ([sécurité](../securite.md), § 1).
- **H.264 annoncé, H.265 servi** : le service média ONVIF 1.0 ne sait pas décrire le H.265 et déclare le flux principal en H.264, alors qu’ArgOS le reçoit en H.265. Le service média 2 décrit le vrai codec. ArgOS continue de lire le codec dans le Flux lui-même ([Caméras H.265](ajouter-une-camera.md#caméras-h265)).

## 5. Précautions avant de modifier

- **Lire, modifier, relire** : noter la valeur d’origine (pour revenir en arrière), envoyer le `Set…`, puis relire pour vérifier que la caméra l’a bien pris.
- **Ne jamais changer** son IP, son mot de passe ni ses ports sans plan de repli : une erreur la rend injoignable, et il ne reste que le bouton de réinitialisation.
- Un changement de **résolution ou de codec** change le Flux : la sonde d’ArgOS suit le codec seule, mais l’Aperçu et le Live peuvent couper quelques secondes.
- Tant qu’il n’y a pas HTTPS, le mot de passe de la caméra passe déjà en clair ou en Digest sur le réseau des caméras (RTSP) ; ONVIF l’envoie en WS-Security (empreinte, pas en clair).
