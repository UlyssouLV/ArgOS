# Paramétrer une Caméra : ONVIF

Comprendre ce qu’on peut régler sur une caméra IP (nom et heure incrustés, horloge, image, vidéo), et comment le faire quand son interface web est inutilisable. Écrit à partir d’une vraie caméra générique branchée sur un Site de dev, en octobre 2026. Depuis la 0.6.0, ArgOS **lit et règle** par ONVIF les Réglages de la Caméra : Incrustations, fuseau de l’Horloge et mise à l’heure du Site. Voir [§ 6](#6-les-réglages-de-la-caméra-dans-argos).

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

- **Horloge au 31/12/1999** : le serveur de temps s’appelle simplement `NTP`, un nom qui ne mène nulle part, et le fuseau est celui de l’Australie (`AWST-8`). L’heure incrustée est fausse, et le serait dans tout enregistrement. Remède : fuseau de Paris (`CET-1CEST,M3.5.0,M10.5.0/3`) et heure du Site, depuis ArgOS ([§ 6](#régler-lhorloge)) ; pas de serveur de temps public, la caméra n’ayant pas accès à internet.
- **DNS chinois** (`114.114.114.114`) : la caméra cherche à joindre internet, comme beaucoup de caméras génériques. Bloquer son accès à internet dans la box ([sécurité](../securite.md), § 1).
- **H.264 annoncé, H.265 servi** : le service média ONVIF 1.0 ne sait pas décrire le H.265 et déclare le flux principal en H.264, alors qu’ArgOS le reçoit en H.265. Le service média 2 décrit le vrai codec. ArgOS continue de lire le codec dans le Flux lui-même ([Caméras H.265](ajouter-une-camera.md#caméras-h265)).

## 5. Précautions avant de modifier

- **Lire, modifier, relire** : noter la valeur d’origine (pour revenir en arrière), envoyer le `Set…`, puis relire pour vérifier que la caméra l’a bien pris.
- **Ne jamais changer** son IP, son mot de passe ni ses ports sans plan de repli : une erreur la rend injoignable, et il ne reste que le bouton de réinitialisation.
- Un changement de **résolution ou de codec** change le Flux : la sonde d’ArgOS suit le codec seule, mais l’Aperçu et le Live peuvent couper quelques secondes.
- Tant qu’il n’y a pas HTTPS, le mot de passe de la caméra passe déjà en clair ou en Digest sur le réseau des caméras (RTSP) ; ONVIF l’envoie en WS-Security (empreinte, pas en clair).

## 6. Les Réglages de la Caméra dans ArgOS

Dans l’Administration, chaque Caméra **active** a un bouton **Réglages** (pas une Caméra désactivée). Il ouvre un panneau qui lit la caméra par ONVIF **à chaque ouverture** : ArgOS ne garde aucune copie de ces réglages, la caméra reste la seule source de vérité. Les Incrustations ([plus bas](#régler-les-incrustations)) et l’Horloge ([fuseau et mise à l’heure](#régler-lhorloge)) se règlent.

### Ce qu’ArgOS lit

- **Horloge** (celle de l’Appareil, partagée par toutes ses Caméras) : date et heure de la caméra (UTC), **écart avec l’heure du Site** (« en retard de 26 ans », « en avance de 3 min »), fuseau, et si la caméra se règle sur un serveur de temps (NTP), avec son nom.
  - Le fuseau est donné par la caméra au format POSIX (`CET-1CEST,M3.5.0,M10.5.0/3`). ArgOS le montre en nom lisible (`Europe/Paris`) s’il le reconnaît parmi les fuseaux courants, sinon tel quel (`AWST-8`).
- **Incrustations** de la **première source vidéo** (premier profil média) :
  - le **nom** : texte, position, affiché ou caché ;
  - la **date et heure** : format (non modifiable), position, affichée ou cachée.
  - Une position hors des quatre coins s’affiche « position personnalisée ».

### Régler les Incrustations

Le panneau est un formulaire. Sous chaque champ reste affichée sa **valeur d’origine** (lue à l’ouverture), jusqu’à la fermeture du panneau : de quoi y revenir à la main.

- **Texte du nom** : texte libre. **Reprendre le nom ArgOS** y copie le nom de la Caméra ; les deux ne sont pas liés ensuite.
- **Position** du nom et de la date et heure : un des quatre coins. Une « position personnalisée » lue sur la caméra est remplacée par le coin choisi.
- **Affichage** :
  - **cacher** une Incrustation la retire de la caméra (`DeleteOSD`), après une confirmation : « Certaines caméras ne permettent pas de la réafficher ensuite. » ;
  - **afficher** une Incrustation cachée la recrée (`CreateOSD`, même type, avec son texte et son coin). C’est proposé **seulement si la caméra annonce savoir la recréer** (`GetOSDOptions`) : sinon ArgOS refuse sans rien envoyer.
- Le **format de la date** ne s’envoie jamais : les caméras ne le règlent pas de façon fiable.

### Régler l’Horloge

L’Horloge est celle de l’Appareil : la régler depuis une Caméra la règle pour toutes les Caméras de la même MAC.

- **Fuseau** : choisi dans une liste de noms lisibles (`Europe/Paris` en tête, puis les fuseaux courants), dans le même formulaire que les Incrustations. ArgOS le convertit au format POSIX qu’attend ONVIF (`Europe/Paris` → `CET-1CEST,M3.5.0,M10.5.0/3`), à partir de la dernière ligne du fichier du fuseau dans la base IANA (paquet `tzdata`), et l’envoie seul (`SetSystemDateAndTime`) en **gardant le mode** de la caméra (manuel ou serveur de temps) et, en manuel, son heure. Un fuseau qu’ArgOS ne reconnaît pas (`AWST-8`) reste affiché tel quel tant qu’on n’en choisit pas un autre. Après l’envoi, le fuseau relu (en POSIX) donne le statut, comme pour les Incrustations.
- **Mettre à l’heure du Site** : un bouton qui envoie **une fois** l’heure UTC du serveur ArgOS à la caméra, en mode manuel, sans toucher à son fuseau, puis relit l’Horloge : date, heure et écart avec le Site se mettent à jour (« en retard de 26 ans » devient « à l’heure » ou quelques secondes). Si la caméra se règle sur un serveur de temps, une confirmation le dit d’abord : « La caméra se règle sur le serveur de temps `<x>`. La mettre à l’heure du Site coupe cette synchronisation. »
- ArgOS n’écrit **jamais** sur l’Horloge sans une action de l’Administrateur : ouvrir les Réglages ne fait que lire, et rien ne remet une caméra à l’heure tout seul. Une caméra laissée en mode manuel dérive : la remettre à l’heure de temps en temps.

**Pourquoi pas de NTP ?** Les Caméras n’ont pas accès à internet (bloqué dans la box, [sécurité](../securite.md), § 1) : un serveur de temps public comme `pool.ntp.org` ne leur répondrait pas, et le leur ouvrir irait contre la page sécurité. ArgOS ne règle donc pas le NTP de la caméra : il le montre seulement (en lecture). Plus tard, le Site deviendra lui-même serveur de temps des Caméras, sur le réseau local (voir la [feuille de route](../dev/feuille-de-route/feuille-de-route-dev.md)).

Par l’API : le fuseau passe par `PATCH /api/cameras/{id}/reglages` (`{"horloge": {"fuseau": "Europe/Paris"}}`, champ `horloge.fuseau` dans la réponse, valeur relue en POSIX ; un nom IANA inconnu → `422`). La mise à l’heure : `POST /api/cameras/{id}/reglages/mise-a-l-heure`, sans corps, qui renvoie l’Horloge relue (écart avec le Site compris). Mêmes erreurs que la lecture (`404`, `502`).

### Envoyer et vérifier

**Enregistrer** n’envoie que les champs modifiés, **chacun séparément** (un refus n’empêche pas les autres), puis **relit** la caméra et affiche, par champ envoyé :

| Statut | Signification |
|---|---|
| « pris » | La valeur relue est celle demandée. |
| « pas pris » | La caméra a accepté sans appliquer : ArgOS montre la valeur qu’elle a gardée. |
| « refusé » | La caméra a refusé le réglage (texte trop long, par exemple), ou ArgOS ne l’a pas envoyé (Incrustation que la caméra ne sait pas recréer). |

**Annuler** remet le formulaire aux valeurs d’origine, sans rien envoyer.

Par l’API : `PATCH /api/cameras/{id}/reglages` avec seulement les champs modifiés (`{"incrustations": {"nom": {"texte": "Entrée"}}}`) ; la réponse donne, pour chaque champ envoyé, la valeur demandée, la valeur relue et le statut (`pris`, `pas_pris`, `refuse`), puis les Réglages relus. Mêmes erreurs que la lecture (`404`, `502`).

### Port et identifiants

- **Port ONVIF** : rien à saisir. À la première ouverture, ArgOS demande l’heure (`GetSystemDateAndTime`, sans identifiants) sur `http://<hôte de l’URL RTSP>:<port>/onvif/device_service`, ports `80`, `8899`, `2000`, `8000`, `8080`, et retient le premier qui répond **en SOAP** (une page web ne compte pas). Ce port est gardé sur la Caméra ; s’il ne répond plus, ArgOS cherche à nouveau. Changer l’URL RTSP de la Caméra l’oublie.
- **Identifiants** : ceux de l’URL RTSP de la Caméra, envoyés en WS-Security (empreinte du mot de passe, jamais en clair). Une URL sans identifiants : requêtes sans authentification.
- Délais courts : quelques secondes par requête.

### Messages

| Message | Cause |
|---|---|
| « Cette caméra ne répond pas en ONVIF » | L’appareil répond sur le réseau, mais aucun port courant ne répond en SOAP (ou sa réponse n’est pas celle qu’ArgOS attend). |
| « La caméra refuse ces identifiants en ONVIF » | Les identifiants de l’URL RTSP sont refusés, ou l’URL n’en a pas et la caméra en exige. |
| « Caméra injoignable » | Rien ne répond à l’adresse de la caméra, même si son état était `online`. |

Pour développer sans matériel, les Caméras simulées 2 (port `8899`, identifiants) et 4 (port `80`, sans identifiants) répondent en ONVIF, « sortie d’usine » comme la caméra de dev : voir `simulation/onvif/README.md` dans le dépôt.
