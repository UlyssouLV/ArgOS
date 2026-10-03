# ArgOS

Plateforme de vidéosurveillance IP auto-hébergée : un Site connaît des Caméras et en montre les Flux.

## Language

**Site** :
Une installation d'ArgOS : les Caméras qu'elle connaît et l'Administrateur qui la gère.
_Avoid_ : instance, serveur, déploiement

**Administrateur** :
Personne qui se connecte au Site avec le compte local pour gérer les Caméras.
_Avoid_ : admin, utilisateur, opérateur

**Caméra** :
Source vidéo connue du Site, identifiée par une URL RTSP.
_Avoid_ : Device, capteur, stream

**Caméra désactivée** :
Caméra que le Site connaît encore mais ne surveille plus.
_Avoid_ : Caméra archivée, Caméra supprimée

**Flux** :
La vidéo RTSP que produit une Caméra.
_Avoid_ : Stream, feed

**Caméra simulée** :
Caméra de dev qui diffuse en boucle une vidéo de dev, en remplacement d’un appareil réel.
_Avoid_ : Flux simulé, fausse caméra, mock

**Détection** :
Action, lancée par l’Administrateur, qui cherche sur le réseau du Site les appareils pouvant devenir des Caméras.
_Avoid_ : scan, découverte

**Candidat** :
Hôte trouvé par une Détection, ou saisi par son IP, qui répond en RTSP et n’est pas (encore) une Caméra du Site.
_Avoid_ : appareil détecté, device

**Aperçu** :
Flux d’un Candidat montré dans l’Administration pendant son ajout, avant qu’il soit une Caméra.
_Avoid_ : preview, prévisualisation

**Live** :
La vue qui montre le Flux d'une seule Caméra active à la fois, avec passage à la suivante.
_Avoid_ : mur d'images, mosaïque, visionneuse
