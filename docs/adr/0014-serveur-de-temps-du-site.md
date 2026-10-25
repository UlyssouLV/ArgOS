# Serveur de temps du Site sur le réseau des caméras

Vue produit (calage, changement d’heure, enregistrements) : [Serveur de temps et calage des Caméras](../features/heure/serveur-de-temps-et-calage.md).

Complète l'[ADR 0003](0003-macvlan-sur-la-prise-des-cameras.md) : le réseau des caméras n'est plus « une sortie seulement ». Un nouveau service **`temps`** (chrony, image `ghcr.io/ulyssoulv/argos-temps`, même canal que les autres images, ADR 0010) y sert l'heure en **NTP, UDP 123, et rien d'autre**, à une **seconde IP fixe** hors DHCP réservée par le script réseau. `api` garde son IP macvlan et n'y sert toujours rien. Sans macvlan (Mac / Docker Desktop, ou install sans le script réseau), `temps` publie `123/udp` sur l'hôte et le Site annonce son IP.

chrony tourne avec **`-x`** : il ne règle jamais l'horloge de l'hôte (pas de `SYS_TIME`), et sert l'heure qu'il estime d'après sa source. Source par défaut `pool.ntp.org`, repli sur l'horloge du serveur quand elle est injoignable ; l'Administrateur la change dans l'Heure du Site. `api` la transmet par un fichier d'un volume partagé, en lecture seule pour `temps`, qui relance chronyd quand il change (lui retirer sa source par `chronyc` ne le ramène pas sur l'horloge du serveur : il garde sa dernière estimation) ; `api` lit la source effectivement servie en interrogeant `temps` en NTP, comme une caméra (identifiant de référence `127.127.1.1` : l'horloge du serveur). Les Caméras sont calées par ONVIF (`SetNTP` manuel vers l'IP annoncée, `SetSystemDateAndTime` en mode NTP au fuseau du Site), jamais par DHCP. Toutes les heures (et sur « Vérifier maintenant »), le Site relit l'Horloge de chaque Caméra active (`GetSystemDateAndTime`, `GetNTP`) : il la recale si elle n'est plus en NTP vers cette IP au fuseau du Site, et signale sans rien faire de plus un écart de plus de 2 s sur une Caméra calée.

## Considered Options

- **Service `temps` dédié, IP macvlan propre** (retenu) : un conteneur qui ne fait que NTP, une seule porte ouverte sur le réseau des caméras, `api` reste fermé.
- **NTP dans `api`, sur son IP macvlan** : pas d'IP de plus, mais l'API (identifiants des caméras, base) deviendrait joignable depuis le réseau des caméras.
- **chrony sur l'hôte Ubuntu** : pas de conteneur, mais hors de l'image et du canal de livraison, non testable en CI, et rien sous Mac.
- **`SYS_TIME` pour recaler l'OS** : corrigerait aussi la datation des Segments, mais donne à un conteneur le pouvoir de changer l'heure de l'hôte, sans effet sous Mac ; inutile pour l'heure servie aux Caméras dès qu'une source externe répond.

## Consequences

- ArgOS occupe **deux** IP sur le réseau des caméras (`api`, `temps`), toutes deux hors de la plage DHCP.
- Un appareil du réseau des caméras peut interroger `temps` : il apprend l'heure du Site, rien d'autre. chrony n'accepte aucune commande depuis ce réseau (`cmdport` fermé hors du réseau Compose).
- Une horloge d'OS fausse ne fausse pas l'heure des Caméras quand la source externe répond, mais date de travers les Segments enregistrés (hors périmètre 0.9.0).
- Sans source externe joignable, toutes les Caméras suivent l'horloge du serveur : communes entre elles, justes seulement si l'hôte l'est.
