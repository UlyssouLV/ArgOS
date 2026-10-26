# Glossaire

Vocabulaire du projet. Une seule source pour les agents, le code-review et le site de documentation. Les termes soulignés en pointillés dans les fiches renvoient ici.

## Site {#site}

Une installation d'ArgOS : les Caméras qu'elle connaît et l'Administrateur qui la gère.

À éviter : instance, serveur, déploiement.

## Administrateur {#administrateur}

Personne qui se connecte au Site avec le compte local pour gérer les Caméras.

À éviter : admin, utilisateur, opérateur.

## Appareil {#appareil}

Matériel réseau reconnu par son adresse MAC, qui porte une ou plusieurs Caméras.

À éviter : device, équipement, hôte.

## Caméra {#camera}

Flux d’un Appareil connu du Site, identifié par une URL RTSP.

À éviter : Device, capteur, stream.

## Incrustation {#incrustation}

Texte que l’Appareil dessine lui-même dans l’image d’une Caméra avant de l’encoder (le nom, la date et heure).

À éviter : OSD, overlay, filigrane.

## Horloge {#horloge}

Date, heure, fuseau et serveur de temps d’un Appareil, partagés par toutes ses Caméras. L’Administrateur ne la règle pas : le Site la cale sur l’Heure du Site.

À éviter : heure système.

## Heure du Site {#heure-du-site}

La source de l’heure et le fuseau du Site, réglés une fois pour toutes ses Caméras. Une Caméra est calée sur le Site quand son Horloge suit le Serveur de temps du Site avec le fuseau du Site, envoyé au décalage du moment (sans règles d’heure d’été), pris dans la base des fuseaux du serveur (embarquée dans ArgOS en secours).

À éviter : heure système, horloge du Site, heure du serveur.

## Serveur de temps du Site {#serveur-de-temps-du-site}

Le service NTP que le Site offre aux Appareils sur le réseau des caméras, à partir de l’Heure du Site.

À éviter : NTP local, horloge du Site.

## Mise à l’heure {#mise-a-l-heure}

Le Site donne à l’Horloge d’une Caméra l’heure du Serveur de temps du Site, puis la cale à nouveau sur le Site. Il le fait à chaque vérification, sans attendre que la Caméra dérive.

À éviter : synchronisation, resynchro.

## Image {#image}

Comment l’Appareil rend ce que voit son capteur (filtre infrarouge, luminosité, contraste, saturation, netteté, contre-jour, WDR), partagée par toutes ses Caméras.

À éviter : imaging, réglages capteur.

## Encodage {#encodage}

Résolution, images par seconde, débit et codec du Flux d’une Caméra.

À éviter : profil, configuration vidéo, stream.

## Réglages de la Caméra {#reglages-de-la-camera}

Ce que l’Administrateur règle sur une Caméra par ONVIF depuis l’Administration : ses Incrustations, l’Image de son Appareil et l’Encodage de son Flux.

À éviter : configuration, paramètres.

## Caméra désactivée {#camera-desactivee}

Caméra que le Site connaît encore mais ne surveille plus.

À éviter : Caméra archivée, Caméra supprimée.

## Flux {#flux}

La vidéo RTSP que produit une Caméra.

À éviter : Stream, feed.

## Caméra simulée {#camera-simulee}

Caméra de dev qui diffuse en boucle une vidéo de dev, en remplacement d’un appareil réel.

À éviter : Flux simulé, fausse caméra, mock.

## Détection {#detection}

Action, lancée par l’Administrateur, qui cherche sur le réseau du Site les appareils pouvant devenir des Caméras.

À éviter : scan, découverte.

## Candidat {#candidat}

Hôte trouvé par une Détection, ou saisi par son IP, qui répond en RTSP et n’est pas (encore) une Caméra du Site.

À éviter : appareil détecté, device.

## Aperçu {#apercu}

Flux d’un Candidat montré dans l’Administration pendant son ajout, avant qu’il soit une Caméra.

À éviter : preview, prévisualisation.

## Live {#live}

La vue qui montre le Flux d'une seule Caméra active à la fois, avec passage à la suivante.

À éviter : mur d'images, mosaïque, visionneuse.

## Session {#session}

Connexion ouverte par l’Administrateur sur un poste, portée par un cookie : sans elle, ni l’API ni les Flux ne répondent.

À éviter : login, token.

## Pont {#pont}

Relais vidéo du Site (MediaMTX) : il lit les Flux des Caméras en RTSP et les sert au navigateur en WebRTC ou en HLS.

À éviter : proxy, serveur média.

## Autorité du Site {#autorite-du-site}

Certificat qui permet à un poste de reconnaître le Site en HTTPS ; installée une fois par poste.

À éviter : CA, certificat racine, certificat auto-signé.

## Certificat de l’Appareil {#certificat-de-l-appareil}

Certificat que l’Appareil présente quand le Site le règle en ONVIF chiffré ; le Site mémorise sa clé au premier contact et refuse ensuite toute autre.

À éviter : empreinte, pin, certificat de la caméra.

## ONVIF en clair {#onvif-en-clair}

Réglages d’une Caméra dont l’Appareil ne propose pas ONVIF chiffré, envoyés sans chiffrement après accord de l’Administrateur.

À éviter : mode HTTP, mode non sécurisé.

## Enregistrement {#enregistrement}

Écriture continue sur disque du Flux d’une Caméra choisie par l’Administrateur, sans réencodage, en segments gérés par le Pont.

À éviter : recording, archive, NVR.

## Segment d’enregistrement {#segment-d-enregistrement}

Fichier fMP4 produit par le Pont pour une plage courte du Flux d’une Caméra en Enregistrement (ordre de la minute), rangé sous le dossier de cette Caméra.

À éviter : chunk, part, clip.

## Conservation {#conservation}

Durée pendant laquelle le Site garde les Segments d’enregistrement avant de les effacer (fenêtre glissante côté Pont). Réglable pour tout le Site.

À éviter : rétention seule, TTL, recordDeleteAfter (terme pont).

## Seuil de place disque {#seuil-de-place-disque}

Marge d’octets libres sur le volume des enregistrements en dessous de laquelle le Site signale un risque de saturation, sans couper l’Enregistrement tout seul.

À éviter : quota, alerte disque, watermark.

## Débit d’écriture {#debit-d-ecriture}

Vitesse à laquelle les Segments d’une Caméra (ou l’ensemble retenu) remplissent le volume : mesurée sur les fichiers récents si possible, sinon estimée d’après l’encodage connu.

À éviter : bitrate Live, débit max ONVIF seul (c’est un repli, pas le concept).

## Relecture {#relecture}

Consultation dans l’UI de l’historique enregistré d’une Caméra : choisir un moment sur la période de Conservation et lire les Segments fermés, sans réencodage, derrière la session.

À éviter : playback seul, VOD, archive player.

## Timeline d’enregistrement {#timeline-d-enregistrement}

Bande temporelle d’un jour (00h → 24h, heure du Site) dans la fenêtre de Conservation d’une Caméra en Relecture : plages où des Segments existent mises en évidence ; un clic positionne la lecture au début du Segment concerné.

À éviter : scrubber Live, curseur media générique.

## Staging {#staging}

Canal d’images du Site sur le registre (`:staging`) : early access de la version en cours (publié depuis la branche de version après review et quality gate, avant `/th` et avant promo Release). Un Site Ubuntu de test ou une machine perso (Docker) peut le suivre.

À éviter : préproduction git, branche staging, serveur de test.

## Production (canal) {#production-canal}

Canal d’images du Site sous l’étiquette semver (`X.Y.Z`) : même digest que le Staging au moment de la promotion manuelle (workflow **Promouvoir images vers Release**). Les Sites Ubuntu « vrais » suivent ce semver, pas `:staging`.

À éviter : branche production, prod git.

Ne pas confondre avec le terme **Image** (réglages capteur d’un Appareil).
