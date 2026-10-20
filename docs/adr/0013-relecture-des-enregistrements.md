# Relecture des enregistrements (transport et granularité)

L’enregistrement continu (ADR 0011) et le suivi stockage (ADR 0012) laissent les segments fMP4 sur le volume sans lecture navigateur. La **Relecture** expose cet historique dans l’UI, derrière la session (ADR 0006), **sans réencodage**.

**Transport : serveur playback du pont, relayé par nginx (tranché par le spike, #129).** MediaMTX sert les Segments qu'il a écrits (`playback: yes`, port `9996` non publié, permission `playback` déjà accordée à `any`). nginx relaie **seulement** `/flux/relecture/get` vers `mediamtx:9996/get`, après le même `auth_request` que `/flux/webrtc/` et `/flux/hls/` (ADR 0006) : `401` sans session valide. Le navigateur demande `/flux/relecture/get?path=camera-<id>&start=<début RFC 3339>&duration=<s>&format=mp4` et reçoit un MP4 progressif lisible par `<video>`. La **liste** des plages vient de l'API (`GET /api/cameras/<id>/segments`, Segments fermés seulement) ; `/list` du serveur playback n'est pas relayé (il renvoie des URL internes `mediamtx:9996`). Spike : Caméras simulées 1 (H.264) et 4 (H.265), Segments fermés relus en `video/mp4`, échantillons `avc1` et `hvc1` du Segment d'origine, **sans réencodage** ; le H.265 se lit donc là où le Live H.265 se lit (`hvc1`, ADR 0004).

**Vidéo seule (0.9.0, bug #141).** Une caméra dont le Flux RTSP annonce une piste audio (PCM `ipcm` 8 kHz, souvent un souffle sans son utile) la voit enregistrée avec la vidéo, et `/get` la muxe dans le MP4 : Chrome lit la vidéo, **Safari refuse le fichier** (« Enregistrement indisponible »). MediaMTX ne sait ni filtrer les pistes à l'enregistrement ni au playback, et son image n'embarque pas ffmpeg. nginx relaie donc `/flux/relecture/get` à l'**API** (`/api/relecture/get`, mêmes paramètres, session exigée), qui relaie `mediamtx:9996/get` en flux et, en `format=mp4`, **retire du `moov` toute piste non vidéo** (`argos_api/relecture.py`) : les tables de morceaux de la vidéo suivent le `moov` raccourci, les octets audio restent inertes dans `mdat`, **sans réencodage** (images décodées identiques). Les Segments du volume gardent leur audio ; anciens comme nouveaux se relisent en vidéo seule. Avec de l'audio, le pont ouvre d'abord un Segment de quelques dixièmes de seconde **audio seul**, avant la première image clé : il est relu tel quel (rien à montrer). La Caméra simulée 4 annonce une telle piste audio (`AUDIO_IPCM`, `media/simulated/diffuser.sh`).

**Granularité timeline (V0.8.2).** Un clic sur la timeline saute au **début du segment** qui couvre l’instant (ou le plus proche). Seek précis à la seconde = refonte **1.0.0** — à ne pas « oublier » en polish UI.

## Considered Options

- **Playback MediaMTX** (retenu) : le pont assemble déjà les fMP4 en MP4 sur une plage `start` + `duration`, même au-delà d'un Segment ; aligne Live et archives sur le même composant ; un `location` nginx de plus.
- **API qui sert les fichiers** : contrôle ArgOS total sur la liste et l’auth ; mais un Segment fMP4 brut ne s'enchaîne pas au suivant sans réassemblage, l'API relaierait des dizaines de Mo par minute, et on réinventerait l'assemblage VOD que le pont fait déjà.
- **Seek précis dès 0.8.2** : meilleur produit, mais index / player plus lourds ; hors du job « simple maintenant, propre en 1.0.0 ».

## Consequences

- ADR 0011 (« pas d’exposition HTTP ») est **levé** pour la relecture authentifiée ; l’inspection volume Docker reste utile en labo, plus la seule voie.
- Les segments **encore ouverts** (écriture en cours) sont exclus de la relecture. Le volume ne marque pas la fermeture : l'API tient le dernier Segment pour ouvert tant que l'Enregistrement est ON et qu'il a été écrit il y a moins de 120 s (2 × `recordSegmentDuration`, même seuil que l'état « en erreur » de l'Enregistrement). Un Segment bloqué au-delà serait proposé ; un Segment tout juste fermé peut rester caché jusqu'à 2 min.
- La timeline se rafraîchit toutes les 10 s : les Segments fermés depuis s'y ajoutent, et l'enchaînement attend le suivant au lieu de s'arrêter au dernier connu.
- Pas de téléchargement / export dans cette décision (Plus tard).
- Le MP4 de relecture traverse l'API (0.9.0) : un flux de plus par lecteur ouvert, sans mise en mémoire au-delà du `moov`. Pas d'audio en relecture tant qu'une fonctionnalité son n'est pas décidée.
- Vitesses de lecture ×1…×16 côté lecteur web ; ×32 hors scope.
- `/get` ne gère pas les plages d'octets (`Accept-Ranges: none`, réponse en flux) : pas de seek HTTP dans un Segment ; le lecteur relit depuis `start` ou charge le Segment entier. Cohérent avec « clic = début de Segment » ; à revoir avec le seek précis (1.0.0).
- Comme le Live, toute session valide relit tout chemin du pont, et un conteneur compromis du réseau Compose joint `9996` sans session (ADR 0006). Ne jamais publier `9996` (`docs/securite.md`).
