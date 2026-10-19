# Relecture des enregistrements (transport et granularité)

L’enregistrement continu (ADR 0011) et le suivi stockage (ADR 0012) laissent les segments fMP4 sur le volume sans lecture navigateur. La **Relecture** expose cet historique dans l’UI, derrière la session (ADR 0006), **sans réencodage**.

**Transport.** Un spike court tranche entre : (1) serveur **playback MediaMTX** (permission déjà présente) derrière nginx `/flux/…` + `auth_request`, ou (2) **API ArgOS** qui liste les plages et sert / proxy les fichiers (ou une playlist) vers un `<video>`. Le chemin retenu est celui qui marche avec H.264 / H.265 comme le Live et reste entièrement derrière la session. Mettre à jour ce paragraphe (ou une ADR suivante) si le spike invalide l’option initiale.

**Granularité timeline (V0.8.2).** Un clic sur la timeline saute au **début du segment** qui couvre l’instant (ou le plus proche). Seek précis à la seconde = refonte **1.0.0** — à ne pas « oublier » en polish UI.

## Considered Options

- **Playback MediaMTX** : le pont assemble déjà les fMP4 ; aligne Live et archives sur le même composant ; ports / config à brancher derrière nginx.
- **API qui sert les fichiers** : contrôle ArgOS total sur la liste et l’auth ; risque de réinventer l’assemblage VOD et le support codec.
- **Seek précis dès 0.8.2** : meilleur produit, mais index / player plus lourds ; hors du job « simple maintenant, propre en 1.0.0 ».

## Consequences

- ADR 0011 (« pas d’exposition HTTP ») est **levé** pour la relecture authentifiée ; l’inspection volume Docker reste utile en labo, plus la seule voie.
- Les segments **encore ouverts** (écriture en cours) sont exclus de la relecture.
- Pas de téléchargement / export dans cette décision (Plus tard).
- Vitesses de lecture ×1…×16 côté lecteur web ; ×32 hors scope.
