/**
 * Termes du glossaire (docs/glossaire.md), du plus long au plus court.
 */
const TERMES_GLOSSAIRE = [
  {
    formes: ['Réglages de la Caméra', 'réglages de la Caméra'],
    slug: 'reglages-de-la-camera',
    resume:
      'Ce que l’Administrateur règle sur une Caméra par ONVIF : Incrustations et Horloge.',
  },
  {
    formes: ['Autorité du Site', 'autorité du Site'],
    slug: 'autorite-du-site',
    resume:
      'Certificat qui permet à un poste de reconnaître le Site en HTTPS.',
  },
  {
    formes: ['Caméra désactivée', 'Caméras désactivées', 'caméra désactivée'],
    slug: 'camera-desactivee',
    resume: 'Caméra que le Site connaît encore mais ne surveille plus.',
  },
  {
    formes: ['Caméra simulée', 'Caméras simulées', 'caméra simulée'],
    slug: 'camera-simulee',
    resume:
      'Caméra de dev qui diffuse en boucle une vidéo à la place d’un appareil réel.',
  },
  {
    formes: ['Administrateur', 'Administrateurs'],
    slug: 'administrateur',
    resume:
      'Personne qui se connecte au Site avec le compte local pour gérer les Caméras.',
  },
  {
    formes: ['Incrustation', 'Incrustations'],
    slug: 'incrustation',
    resume:
      'Texte que l’Appareil dessine dans l’image d’une Caméra avant de l’encoder.',
  },
  {
    formes: ['Détection', 'Détections'],
    slug: 'detection',
    resume:
      'Action qui cherche sur le réseau du Site les appareils pouvant devenir des Caméras.',
  },
  {
    formes: ['Candidat', 'Candidats'],
    slug: 'candidat',
    resume:
      'Hôte trouvé par une Détection (ou saisi par IP) qui répond en RTSP.',
  },
  {
    formes: ['Appareil', 'Appareils'],
    slug: 'appareil',
    resume:
      'Matériel réseau reconnu par son adresse MAC, portant une ou plusieurs Caméras.',
  },
  {
    formes: ['Aperçu'],
    slug: 'apercu',
    resume:
      'Flux d’un Candidat montré dans l’Administration pendant son ajout.',
  },
  {
    formes: ['Horloge'],
    slug: 'horloge',
    resume:
      'Date, heure, fuseau et serveur de temps d’un Appareil, partagés par ses Caméras.',
  },
  {
    formes: ['Caméra', 'Caméras'],
    slug: 'camera',
    resume: 'Flux d’un Appareil connu du Site, identifié par une URL RTSP.',
  },
  {
    formes: ['Flux'],
    slug: 'flux',
    resume: 'La vidéo RTSP que produit une Caméra.',
  },
  {
    formes: ['Live'],
    slug: 'live',
    resume: 'Vue qui montre le Flux d’une seule Caméra active à la fois.',
  },
  {
    formes: ['Site', 'Sites'],
    slug: 'site',
    resume:
      'Une installation d’ArgOS : les Caméras qu’elle connaît et l’Administrateur qui la gère.',
  },
];

module.exports = {TERMES_GLOSSAIRE};
