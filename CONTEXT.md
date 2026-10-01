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
Caméra dont le Flux est produit par MediaMTX à partir d’une vidéo de dev, en remplacement d’un appareil réel.
_Avoid_ : Flux simulé, fausse caméra, mock
