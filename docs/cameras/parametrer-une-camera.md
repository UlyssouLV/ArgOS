# Paramétrer une Caméra : ONVIF

Comprendre ce qu’on peut régler sur une caméra IP (nom et heure incrustés, horloge, image, vidéo), et comment le faire quand son interface web est inutilisable. Écrit à partir d’une vraie caméra générique branchée sur un Site de dev, en octobre 2026. Depuis la 0.6.0, ArgOS **lit et règle** par ONVIF les Réglages de la Caméra : Incrustations (et, jusqu’à la 0.9.0, fuseau de l’Horloge et mise à l’heure du Site). Depuis la 0.6.3, il le fait en **HTTPS** quand la caméra le propose, et en clair seulement avec l’accord de l’Administrateur. Depuis la 0.6.4, il règle aussi l’**Image** de l’Appareil (filtre infrarouge, luminosité, contraste, saturation, netteté, contre-jour, WDR) et l’**Encodage** du Flux de la Caméra (résolution, images par seconde, débit), et montre le Flux dans le panneau. Depuis la 0.9.0, l’heure ne se règle plus Caméra par Caméra : le Site cale chaque Caméra sur son **Heure du Site** ([plus bas](#lheure-de-la-caméra)). Voir [§ 6](#6-les-réglages-de-la-caméra-dans-argos).

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

Le service d’entrée est `https://<ip>/onvif/device_service` quand la caméra propose ONVIF en HTTPS (port `443`, certificat auto-signé), sinon `http://<ip>:<port>/onvif/device_service`. En HTTP, le port **varie selon le fabricant** : `80` chez beaucoup, **`8899`** sur les caméras XiongMai, `2000` ou `8000` ailleurs. Une page web qui répond `200` sur `/onvif/device_service` ne prouve rien : il faut une réponse SOAP. Demander l’heure ne demande aucun identifiant :

```bash
B='<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>'
for p in 80 8899 2000 8000 8080; do
  echo "$p: $(curl -s -m 3 -X POST -H 'Content-Type: application/soap+xml' -d "$B" http://192.168.1.103:$p/onvif/device_service | head -c 80)"
done
# 8899: <?xml version="1.0" encoding="UTF-8"?><s:Envelope ...   ← le bon port
# HTTPS (certificat auto-signé : -k n'en vérifie pas l'autorité)
echo "443: $(curl -sk -m 3 -X POST -H 'Content-Type: application/soap+xml' -d "$B" https://192.168.1.103/onvif/device_service | head -c 80)"
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

- **Incrustations** (OSD) : deux. Le **nom** (texte libre, `CAM01`, en haut à gauche) et la **date et heure** (`yyyy-MM-dd HH:mm:ss`, en bas à gauche). On peut changer le texte, déplacer l’une ou l’autre (un coin ou une position libre), ou les retirer. Ni police, ni taille, ni couleur, ni autre format de date.
- **Horloge** : fuseau, serveur de temps (NTP), ou heure manuelle.
- **Image** : luminosité, contraste, saturation, netteté, compensation de contre-jour, WDR, exposition, balance des blancs, **filtre infrarouge** (jour, nuit, automatique).
- **Vidéo** : résolution (720p, 1080p, 2304×1296), jusqu’à 22 images par seconde, débit, qualité, intervalle entre images clés.
- **PTZ** et **événements** (détection de mouvement, probablement) : annoncés, à étudier ; ce modèle n’a sans doute pas de moteur.

### Ce qui cloche, réglé d’usine

- **Horloge au 31/12/1999** : le serveur de temps s’appelle simplement `NTP`, un nom qui ne mène nulle part, et le fuseau est celui de l’Australie (`AWST-8`). L’heure incrustée est fausse, et le serait dans tout enregistrement. Remède : le Site la cale sur son Serveur de temps, au fuseau du Site ([§ 6](#lheure-de-la-caméra)) ; pas de serveur de temps public, la caméra n’ayant pas accès à internet.
- **DNS chinois** (`114.114.114.114`) : la caméra cherche à joindre internet, comme beaucoup de caméras génériques. Bloquer son accès à internet dans la box ([sécurité](../securite.md), § 1).
- **H.264 annoncé, H.265 servi** : le service média ONVIF 1.0 ne sait pas décrire le H.265 et déclare le flux principal en H.264, alors qu’ArgOS le reçoit en H.265. Le service média 2 décrit le vrai codec. ArgOS continue de lire le codec dans le Flux lui-même ([Caméras H.265](ajouter-une-camera.md#caméras-h265)).

## 5. Précautions avant de modifier

- **Lire, modifier, relire** : noter la valeur d’origine (pour revenir en arrière), envoyer le `Set…`, puis relire pour vérifier que la caméra l’a bien pris.
- **Ne jamais changer** son IP, son mot de passe ni ses ports sans plan de repli : une erreur la rend injoignable, et il ne reste que le bouton de réinitialisation.
- Un changement de **résolution ou de codec** change le Flux : la sonde d’ArgOS suit le codec seule, mais l’Aperçu et le Live peuvent couper quelques secondes. ArgOS demande confirmation avant tout changement d’Encodage, et ne change jamais le codec ([§ 6](#régler-lencodage-du-flux)).
- Le mot de passe de la caméra passe déjà en clair ou en Digest sur le réseau des caméras (RTSP). ONVIF l’envoie en WS-Security (empreinte SHA-1, pas en clair) : à l’abri en HTTPS, lisible et cassable hors ligne s’il est faible en HTTP ([§ 6](#sécurité-de-léchange)).

## 6. Les Réglages de la Caméra dans ArgOS

Dans l’Administration, chaque Caméra **active** a un bouton **Réglages** (pas une Caméra désactivée). Il ouvre un panneau qui lit la caméra par ONVIF **à chaque ouverture** : ArgOS ne garde aucune copie de ces réglages, la caméra reste la seule source de vérité. Les Incrustations ([plus bas](#régler-les-incrustations)), l’Image ([filtre infrarouge, luminosité…](#régler-limage)) et l’Encodage du Flux ([résolution, images par seconde, débit](#régler-lencodage-du-flux)) se règlent. L’heure n’y est pas : elle se règle pour le Site ([L’heure de la Caméra](#lheure-de-la-caméra)).

En tête du panneau, un petit lecteur montre le **Flux de la Caméra**, comme le Live (WebRTC, ou HLS pour un Flux H.265), avec les mêmes messages (« Flux indisponible », « Ce navigateur ne lit pas le H.265 ») : l’effet d’un réglage se voit sans quitter l’Administration. Après une coupure (changement d’Encodage, caméra qui redémarre), il reprend seul, sans recharger la page. Fermer le panneau arrête la lecture.

### Ce qu’ArgOS lit

- **Incrustations** de la **première source vidéo** (premier profil média) :
  - le **nom** : texte, position, affiché ou caché ;
  - la **date et heure** : format (non modifiable), position, affichée ou cachée.
  - Une position hors des quatre coins s’affiche « position personnalisée ».
- **Image** (celle de l’Appareil, partagée par toutes ses Caméras) de la **première source vidéo**, par le service image ONVIF : seulement les paramètres que la caméra annonce (`GetOptions`), avec leurs bornes.
- **Encodage du Flux** (celui de la Caméra) : le profil dont l’URL de flux correspond à l’URL RTSP de la Caméra, ses résolution, images par seconde, débit max, codec, qualité et intervalle entre images clés, et ce que la caméra propose.

### Régler les Incrustations

Le panneau est un formulaire. Sous chaque champ reste affichée sa **valeur d’origine** (lue à l’ouverture), jusqu’à la fermeture du panneau : de quoi y revenir à la main.

- **Texte du nom** : texte libre. **Reprendre le nom ArgOS** y copie le nom de la Caméra ; les deux ne sont pas liés ensuite.
- **Position** du nom et de la date et heure : un des quatre coins. Une « position personnalisée » lue sur la caméra est remplacée par le coin choisi.
- **Affichage** :
  - **cacher** une Incrustation la retire de la caméra (`DeleteOSD`), après une confirmation : « Certaines caméras ne permettent pas de la réafficher ensuite. » ;
  - **afficher** une Incrustation cachée la recrée (`CreateOSD`, même type, avec son texte et son coin). C’est proposé **seulement si la caméra annonce savoir la recréer** (`GetOSDOptions`) : sinon ArgOS refuse sans rien envoyer.
- Le **format de la date** ne s’envoie jamais : les caméras ne le règlent pas de façon fiable.

### L’heure de la Caméra

L’heure ne se règle plus dans les Réglages de la Caméra (section Horloge, fuseau et bouton « Mettre à l’heure du Site » retirés en 0.9.0). Elle se règle **une fois pour le Site**, dans **Administration → Heure du Site** : source de l’heure (`pool.ntp.org` par défaut, ou l’horloge du serveur) et fuseau (celui du serveur par défaut). Le Site sert cette heure en NTP sur le réseau des caméras (le **Serveur de temps du Site**, [ADR 0014](../adr/0014-serveur-de-temps-du-site.md)) et **cale** chaque Caméra ONVIF dessus : serveur NTP = le Site, mode NTP, fuseau du Site.

À chaque vérification — à l’ajout, à chaque changement de l’Heure du Site, puis toutes les heures (et sur « Vérifier maintenant ») — le Site ne se contente pas du NTP de la caméra, qui peut ne se synchroniser qu’à son démarrage : il **met la Caméra à l’heure** ([ADR 0015](../adr/0015-mise-a-l-heure-a-chaque-verification.md)). Il lit l’heure que sert le Serveur de temps du Site, relit l’Horloge de la caméra (sa **dérive**), y pousse cette heure en mode manuel, la recale (serveur NTP = le Site, mode NTP, fuseau du Site), puis la relit (son **écart**). Dérive et écart se mesurent contre l’heure du Serveur de temps du Site. Le tableau de la page Heure du Site donne, pour chaque Caméra, son état, sa dérive, son écart et la date de la dernière vérification :

- **à l’heure** : écart relu de 2 s au plus ;
- **écart** : plus de 2 s, par exemple une caméra qui refuse l’heure poussée (elle est recalée quand même, et le refus est journalisé) ;
- **sans ONVIF** : voir ci-dessous ;
- **échec** : caméra injoignable ou qui refuse ses identifiants, ou Serveur de temps du Site injoignable (la caméra est alors recalée sans être mise à l’heure, dérive et écart restent vides).

Une dérive qui revient à chaque vérification, même quand la Caméra est « à l’heure », montre une caméra qui ne se synchronise pas seule. L’Horloge est celle de l’Appareil : la caler depuis une Caméra la cale pour toutes les Caméras de la même MAC.

**Caméra sans ONVIF** (ou ONVIF en clair non accordé) : marquée « sans ONVIF » dans ce tableau, le Site ne peut pas la caler. La régler à la main, dans son interface web ou l’application du fabricant :

1. Relever l’**Adresse du Serveur de temps** sur la page Heure du Site (l’IP fixe de `temps` sur la prise des caméras, ou l’IP du Site sans macvlan).
2. Dans la caméra, choisir la synchronisation par **serveur NTP**, saisir cette adresse comme serveur (pas `pool.ntp.org` : la caméra n’a pas accès à internet), port `123` si demandé.
3. Choisir le **fuseau du Site** (celui affiché sur la page Heure du Site).

Le Site ne vérifie pas cette caméra : si elle repart en heure manuelle (remise en usine, coupure), recommencer.

Par l’API : `GET /api/cameras/{id}/reglages` rend toujours l’Horloge lue (date, écart avec le Site, fuseau, mode, serveur NTP), en lecture seule. `POST /api/cameras/{id}/reglages/mise-a-l-heure` n’existe plus (`404`), et `horloge` n’est plus accepté par `PATCH /api/cameras/{id}/reglages` (`422`, rien n’est envoyé).

### Régler l’Image

L’Image est celle de l’Appareil : la section le rappelle (« Partagée par les Caméras de cet Appareil : la régler ici la règle pour chacune. »). Chaque paramètre n’apparaît que si la caméra l’annonce :

- **Filtre infrarouge** : jour (filtre posé, image en couleurs ; `ON` en ONVIF), nuit (filtre retiré, vision de nuit ; `OFF`) ou automatique (`AUTO`), parmi les modes que la caméra propose.
- **Luminosité**, **contraste**, **saturation**, **netteté** : des curseurs bornés par la caméra (souvent 0 à 100), avec la valeur chiffrée et la valeur d’origine.
- **Contre-jour** et **WDR** : coupé ou activé, et leur **niveau** (curseur) seulement si la caméra le borne ; sinon le mode seul.
- Exposition, balance des blancs, mise au point : ni lues, ni envoyées.

Sans service image, ou s’il répond en faute, la section dit « Image non réglable sur cette caméra » : le reste du panneau (Incrustations, Encodage) se lit et se règle normalement. L’Image s’envoie avec « Enregistrer » (un `SetImagingSettings` par paramètre, le niveau avec son mode), puis la caméra est relue une fois : mêmes statuts que les Incrustations. Certaines caméras acceptent le WDR sans l’appliquer : il est alors « pas pris ».

Par l’API : la lecture renvoie `image` (`reglable`, `raison` = `non_reglable` sinon `null`, `valeurs`, `options`), avec les champs `infrarouge`, `luminosite`, `contraste`, `saturation`, `nettete`, `contre_jour`, `contre_jour_niveau`, `wdr`, `wdr_niveau` (`null` : non proposé). La modification : `{"image": {"infrarouge": "OFF", "luminosite": 70}}`, champs `image.infrarouge`… dans la réponse. Une valeur hors des bornes relues, un mode ou un paramètre que la caméra ne propose pas → `422`, **rien n’est envoyé** (pas même les autres champs).

### Régler l’Encodage du Flux

L’Encodage est celui du **Flux de la Caméra** : ArgOS cherche, parmi les profils de la caméra (`GetProfiles`), celui dont l’URL de flux (`GetStreamUri`) a **le même chemin et la même requête** que l’URL RTSP de la Caméra (hôte, port et identifiants ignorés). La Caméra du flux secondaire (`…subtype=1`) règle donc le flux secondaire, celle du flux principal le flux principal. Aucun profil ne correspond (URL saisie avec un autre chemin, une requête en plus) : « Encodage introuvable pour ce Flux », rien à régler.

- **Résolution** : parmi celles que la caméra propose.
- **Images par seconde** et **débit max** (kbit/s) : bornés par la caméra ; hors des bornes, « Enregistrer » reste grisé.
- **Codec**, **qualité** et **intervalle entre images clés** : affichés, jamais changés. À l’envoi, ArgOS renvoie ceux qu’il vient de relire.

Par quel service ([ADR 0008](../adr/0008-encodage-par-media-2-media-1-seulement-en-h264.md)) :

- le **média 2** d’ONVIF quand la caméra l’annonce (`GetServices`) : il décrit le vrai codec, H.265 compris ;
- sinon le **média 1**, **seulement si le Flux est en H.264** (codec lu dans le Flux par ArgOS) : le média 1 ne connaît pas le H.265 et le déclare souvent en H.264 (c’est le cas de la caméra de dev), si bien qu’un réglage par lui pourrait changer le codec du Flux ;
- sinon, « Encodage non réglable sur cette caméra » : les valeurs restent affichées, en lecture seule. Le codec affiché est alors celui du Flux.

Un changement d’Encodage **coupe le Flux quelques secondes** (la caméra relance son encodeur). « Enregistrer » le confirme d’abord : « Le Flux de cette Caméra sera coupé quelques secondes. » (**Couper le Flux et enregistrer** ou **Garder le Flux**). Une modification d’Image ou d’Incrustation seule part sans confirmation. L’Encodage part en dernier ; ArgOS relit ensuite la caméra toutes les 2 s environ, jusqu’à ce qu’elle réponde, 20 s au plus. Si elle ne répond plus : « pas pris — la caméra n’a pas répondu après l’envoi », et le formulaire garde les valeurs lues avant l’envoi.

Par l’API : la lecture renvoie `encodage` (`reglable`, `raison` = `profil_introuvable` ou `non_reglable` sinon `null`, `profil`, `valeurs` avec `resolution` (`1920x1080`), `images_par_seconde`, `debit_max`, `codec`, `qualite`, `intervalle_images_cles`, et `options` avec `resolutions`, `images_par_seconde` et `debit_max` (bornes)). La modification : `{"encodage": {"resolution": "1920x1080", "images_par_seconde": 15, "debit_max": 2048}}`, champs `encodage.resolution`… dans la réponse ; sans réponse de la caméra après l’envoi, chaque champ envoyé est `pas_pris` avec `"raison": "sans_reponse"`. Une résolution non proposée, une valeur hors des bornes relues, un champ inconnu ou un Encodage non réglable → `422`, **rien n’est envoyé**.

### Limites

- **H.265 sans média 2** : une caméra dont le Flux est en H.265 et qui n’annonce pas le média 2 a son Encodage en lecture seule (« Encodage non réglable sur cette caméra »). Le média 1 ne sait pas décrire le H.265 : un réglage par lui risquerait de repasser le Flux en H.264 sans le dire ([ADR 0008](../adr/0008-encodage-par-media-2-media-1-seulement-en-h264.md)). Régler cette caméra par l’application du fabricant, ou attendre un firmware qui annonce le média 2.
- **Codec, qualité, intervalle entre images clés** : affichés, jamais modifiables depuis ArgOS.
- **Exposition, balance des blancs, mise au point** : ni lues, ni réglées. La caméra garde les siennes.
- **Image partagée** : l’Image est celle de l’Appareil. La régler depuis une Caméra la change pour toutes les Caméras de la même MAC (flux principal et secondaire compris).
- **Première source vidéo** seulement : l’Image (comme les Incrustations) est celle de la première source vidéo de l’Appareil. Les rares appareils à plusieurs capteurs n’ont que le premier de réglable.

### Envoyer et vérifier

**Enregistrer** n’envoie que les champs modifiés, **chacun séparément** (un refus n’empêche pas les autres), puis **relit** la caméra et affiche, par champ envoyé, la valeur demandée, la valeur relue et le statut :

| Statut | Signification |
|---|---|
| « pris » | La valeur relue est celle demandée. |
| « pas pris » | La caméra a accepté sans appliquer : la valeur relue est celle qu’elle a gardée. Ou, après un envoi d’Encodage, elle n’a plus répondu dans les 20 s (« la caméra n’a pas répondu après l’envoi »). |
| « refusé » | La caméra a refusé le réglage (texte trop long, par exemple), ou ArgOS ne l’a pas envoyé (Incrustation que la caméra ne sait pas recréer). |

**Annuler** remet le formulaire aux valeurs d’origine, sans rien envoyer, et efface les statuts du dernier envoi.

Par l’API : `PATCH /api/cameras/{id}/reglages` avec seulement les champs modifiés (`{"incrustations": {"nom": {"texte": "Entrée"}}}`) ; la réponse donne, pour chaque champ envoyé, la valeur demandée, la valeur relue et le statut (`pris`, `pas_pris`, `refuse`), puis les Réglages relus. Mêmes erreurs que la lecture (`404`, `502`).

### Sécurité de l’échange

ArgOS règle la caméra en **HTTPS** quand elle le propose, et ne la règle en clair qu’avec l’accord de l’Administrateur ([ADR 0007](../adr/0007-onvif-en-https-par-cle-memorisee.md), [sécurité](../securite.md#onvif--réglages-chiffrés-clé-de-lappareil-mémorisée)). Le Live, l’état et le reste de l’Administration n’en dépendent jamais : seuls les Réglages de cette Caméra peuvent être bloqués.

#### Échange chiffré

À la première ouverture des Réglages d’une caméra qui répond en HTTPS, ArgOS mémorise la **clé** de son certificat, le **Certificat de l’Appareil** (empreinte SHA-256 de la clé publique), sans rien demander : c’est le premier contact. Un bandeau le rappelle ensuite à chaque ouverture :

> Échange chiffré (HTTPS). Certificat de l’Appareil `3f2a 9c41 07be d5e8`, mémorisé le 16/10/2026.

L’empreinte est abrégée (16 premiers chiffres) ; elle s’affiche en entier au survol. Une caméra qui renouvelle son certificat en gardant sa clé ne change rien.

Une caméra qui ne propose que **TLS 1.0 ou 1.1** reste réglée en HTTPS, avec un avertissement dans le bandeau : « TLS ancien : la caméra ne propose que TLS 1.0 ou 1.1, des versions dépassées. L’échange reste chiffré, avec la clé mémorisée. » Mettre à jour son firmware, si le fabricant en propose un.

#### Certificat changé

Si la caméra présente une **autre clé** que celle mémorisée, ArgOS s’arrête avant d’envoyer quoi que ce soit avec ses identifiants, et les Réglages affichent, à la place du formulaire :

- « Le certificat de cette caméra a changé. » ;
- **Certificat mémorisé** (empreinte entière et date) et **Certificat présenté** (empreinte entière), par groupes de 4 chiffres pour les comparer ;
- les causes possibles : remise en usine, nouveau firmware, autre appareil à cette adresse.

**Faire confiance au nouveau certificat**, si l’on sait pourquoi il a changé, demande une confirmation (« ArgOS réglera cette caméra avec le certificat `…` et refusera l’ancien. Ne le faites que si vous savez pourquoi il a changé. ») : **Confirmer la confiance** mémorise la nouvelle clé et relit la caméra ; **Annuler** ne change rien. ArgOS vérifie que la caméra présente encore le certificat montré : sinon, « La caméra ne présente plus ce certificat : rouvrir ses Réglages. » Sans savoir pourquoi, ne pas faire confiance : vérifier d’abord l’appareil à cette adresse (MAC, interface de la caméra).

#### HTTPS indisponible

Une Caméra déjà réglée en HTTPS qui ne répond plus qu’en HTTP n’est **jamais** réglée en clair : « Cette caméra ne répond plus en HTTPS : ArgOS refuse de la régler en clair. » Causes possibles : remise en usine, nouveau firmware, autre appareil à cette adresse, ou quelqu’un qui bloque HTTPS pour lire l’échange en clair. **Oublier le certificat de cette caméra** efface la clé et le contact retenus, puis relit : la caméra repart de zéro, comme à son premier contact (HTTPS s’il revient, sinon l’accord ci-dessous).

#### ONVIF en clair

Une caméra qui ne propose **pas** HTTPS n’est réglée en HTTP qu’avec l’accord de l’Administrateur. Avant, seule la recherche du port lui est parvenue (l’heure, demandée sans identifiants), et les Réglages affichent : « Cette caméra ne propose pas HTTPS : ONVIF en clair non accepté. », avec ce que la régler quand même ferait passer en clair (mot de passe en empreinte, cassable hors ligne s’il est faible, et réglages, lisibles et modifiables au passage).

- **Régler quand même en clair** : l’accord est mémorisé pour cette Caméra, et les Réglages s’ouvrent. Il n’est plus redemandé.
- Un bandeau le rappelle à chaque ouverture : « ONVIF en clair : cette caméra ne propose pas HTTPS. Le mot de passe (en empreinte) et les réglages passent en clair sur le réseau des caméras. »
- **Mot de passe court** : si le mot de passe de l’URL RTSP a moins de 12 caractères, le bandeau l’ajoute : « Mot de passe court (moins de 12 caractères) : son empreinte (SHA-1, imposé par la norme), qui passe ici en clair, se casse hors ligne. Mieux vaut un mot de passe d’au moins 12 caractères, sur la caméra puis dans l’URL de la Caméra. » Rien de tel en HTTPS, ni pour une caméra sans identifiants.
- **Retirer l’accord ONVIF en clair** : la Caméra redemande l’accord à l’ouverture suivante.
- Si la caméra se met un jour à proposer HTTPS (nouveau firmware), ArgOS y passe de lui-même et mémorise sa clé : le bandeau devient celui de l’échange chiffré.

### Port et identifiants

- **Contact ONVIF** : rien à saisir. À chaque ouverture (et à chaque envoi), ArgOS demande l’heure (`GetSystemDateAndTime`, sans identifiants) en HTTPS, sur `https://<hôte de l’URL RTSP>/onvif/device_service` (port `443`). Sans réponse SOAP en HTTPS, il essaie le port HTTP retenu, puis les ports `80`, `8899`, `2000`, `8000`, `8080`, et retient le premier qui répond **en SOAP** (une page web ne compte pas). Une Caméra retenue en HTTP passe en HTTPS dès que sa caméra le propose.
- **Adresses des services** : la caméra annonce l’adresse de son service média, souvent en `http://…` même jointe en HTTPS. ArgOS n’en garde que le chemin, et la joint avec le schéma, l’hôte et le port retenus : rien ne repart en clair.
- **Ce qui est gardé** sur la Caméra : schéma et port, clé du Certificat de l’Appareil et sa date, accord ONVIF en clair. Gardés quand on ne change que le mot de passe ou le chemin de l’URL RTSP, et quand la Caméra change d’IP, retrouvée par sa MAC ; **oubliés** quand on change l’hôte de l’URL à la main (tout repart du premier contact).
- **Identifiants** : ceux de l’URL RTSP de la Caméra, envoyés en WS-Security (empreinte du mot de passe, jamais en clair). Une URL sans identifiants : requêtes sans authentification.
- Délais courts : quelques secondes par requête.

Par l’API (session exigée) : la lecture (`GET /api/cameras/{id}/reglages`) renvoie aussi `securite` (`chiffre`, `empreinte`, `empreinte_memorisee_le`, `tls_ancien`, `mot_de_passe_court`). Un refus est un `502` avec son `code` (`certificat_change`, `https_indisponible`, `en_clair_non_accepte`) ; `certificat_change` porte `certificat` (`empreinte_memorisee`, `empreinte_memorisee_le`, `empreinte_presentee`). Les décisions : `POST /api/cameras/{id}/reglages/certificat` (`{"empreinte": "<empreinte présentée>"}`, `409` si la caméra ne la présente plus), `DELETE /api/cameras/{id}/reglages/certificat` (oublier), `PUT` et `DELETE /api/cameras/{id}/reglages/onvif-en-clair` (accord, retrait).

Chaque refus (certificat changé, HTTPS indisponible) et chaque décision (confiance, oubli, accord, retrait) laisse une ligne dans les journaux de l’API, avec l’id de la Caméra et les empreintes, jamais d’identifiant ni d’URL :

```bash
docker compose logs api | grep ONVIF
# (empreintes abrégées ici ; les journaux les donnent entières)
# WARNING:  ONVIF : Caméra 3, certificat changé (mémorisé 3f2a…, présenté 81c0…) : refusé
# INFO:     ONVIF : Caméra 3, confiance au nouveau certificat 81c0… (remplace 3f2a…)
```

### Messages

| Message | Cause |
|---|---|
| « Cette caméra ne répond pas en ONVIF » | L’appareil répond sur le réseau, mais aucun port courant ne répond en SOAP (ou sa réponse n’est pas celle qu’ArgOS attend). |
| « La caméra refuse ces identifiants en ONVIF » | Les identifiants de l’URL RTSP sont refusés, ou l’URL n’en a pas et la caméra en exige. |
| « Caméra injoignable » | Rien ne répond à l’adresse de la caméra, même si son état était `online`. |
| « Le certificat de cette caméra a changé. » | La caméra présente une autre clé que celle mémorisée ([Certificat changé](#certificat-changé)). |
| « Cette caméra ne répond plus en HTTPS : ArgOS refuse de la régler en clair. » | Caméra déjà réglée en HTTPS qui ne répond plus qu’en HTTP ([HTTPS indisponible](#https-indisponible)). |
| « Cette caméra ne propose pas HTTPS : ONVIF en clair non accepté. » | Caméra sans HTTPS, pas encore d’accord de l’Administrateur ([ONVIF en clair](#onvif-en-clair)). |
| « Image non réglable sur cette caméra » | La caméra n’annonce pas de service image, ou il répond en faute ; le reste des Réglages fonctionne ([Régler l’Image](#régler-limage)). |
| « Encodage introuvable pour ce Flux » | Aucun profil de la caméra n’a l’URL de flux de la Caméra (chemin et requête) ([Régler l’Encodage du Flux](#régler-lencodage-du-flux)). |
| « Encodage non réglable sur cette caméra » | La caméra n’a pas de média 2 et son Flux n’est pas en H.264 (ou son codec n’est pas encore connu) : Encodage en lecture seule ([Limites](#limites)). |
| « pas pris — la caméra n’a pas répondu après l’envoi » | Après un changement d’Encodage, la caméra n’a plus répondu dans les 20 s. Rouvrir les Réglages un peu plus tard pour voir ce qu’elle a gardé. |

Pour développer sans matériel, les Caméras simulées 2, 4 et 5 répondent en ONVIF, « sortie d’usine » comme la caméra de dev : la 2 en HTTPS sur `443` (certificat auto-signé, gardé d’un démarrage à l’autre) et en HTTP sur `8899`, avec identifiants, et ArgOS doit choisir HTTPS ; la 4 en HTTP seulement sur `80`, sans identifiants : elle demande l’accord ONVIF en clair. La 2 a un service image (WDR accepté sans être appliqué : « pas pris ») et le média 2, avec deux profils aux chemins de son URL RTSP ; la 4 n’a ni l’un ni l’autre, et son Flux est en H.265 (« Image non réglable sur cette caméra », « Encodage non réglable sur cette caméra »). La 5 est comme la 4, en H.264, et « NTP paresseux » : elle ne se cale sur le Serveur de temps du Site qu’au démarrage et quand elle reçoit son serveur NTP, puis son horloge dérive d’une minute par heure, jusqu’à la prochaine vérification. Voir `simulation/onvif/README.md` dans le dépôt.
