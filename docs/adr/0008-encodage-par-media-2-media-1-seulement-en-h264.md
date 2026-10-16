# Encodage réglé par le média 2, média 1 seulement en H.264

Depuis la 0.6.4, le Site règle l'Encodage d'une Caméra (résolution, images par seconde, débit) par le **service média 2** d'ONVIF quand l'Appareil l'annonce. Sans média 2, il ne passe par le média 1 que si le Flux de la Caméra est en **H.264** (codec lu dans le Flux, déjà connu du Site) ; sinon l'Encodage reste en lecture seule (« Encodage non réglable sur cette caméra »). À l'envoi, le codec, la qualité et l'intervalle entre images clés relus sont renvoyés tels quels.

## Considered Options

- **Média 1 partout** (le seul service que le Site parlait en 0.6.0) : le média 1 ne connaît pas le H.265. La caméra de dev y déclare en H.264 un flux servi en H.265 ; un `SetVideoEncoderConfiguration` renvoyant ce « H.264 » peut repasser le Flux en H.264 ou être refusé. L'Administrateur qui baisse un débit changerait alors le codec, donc le transport du Live (ADR 0004), sans l'avoir demandé.
- **Média 2 seulement** : plus simple, mais prive de réglage d'Encodage les caméras H.264 anciennes qui n'ont que le média 1, et qui le décrivent correctement.
- **Média 1 en H.265 malgré tout, en vérifiant le codec après coup** : le mal serait fait (Flux coupé, codec changé) avant que la relecture le montre.

## Consequences

- Une caméra H.265 sans média 2 ne voit pas son Encodage réglé par ArgOS ; l'écran le dit.
- Le Site parle deux services média ; le choix se fait à chaque lecture des Réglages, d'après `GetServices` et le codec de la Caméra.
- Les Incrustations restent en média 1 (0.6.0) : elles ne dépendent pas du codec.
