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

Date, heure, fuseau et serveur de temps d’un Appareil, partagés par toutes ses Caméras.

À éviter : heure système.

## Image {#image}

Comment l’Appareil rend ce que voit son capteur (filtre infrarouge, luminosité, contraste, saturation, netteté, contre-jour, WDR), partagée par toutes ses Caméras.

À éviter : imaging, réglages capteur.

## Encodage {#encodage}

Résolution, images par seconde, débit et codec du Flux d’une Caméra.

À éviter : profil, configuration vidéo, stream.

## Réglages de la Caméra {#reglages-de-la-camera}

Ce que l’Administrateur règle sur une Caméra par ONVIF depuis l’Administration : ses Incrustations, l’Horloge et l’Image de son Appareil, et l’Encodage de son Flux.

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
