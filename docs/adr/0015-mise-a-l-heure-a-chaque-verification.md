# Mise à l’heure des Caméras à chaque vérification

Complète l'[ADR 0014](0014-serveur-de-temps-du-site.md) : une Caméra calée (mode NTP vers le Serveur de temps du Site, fuseau du Site) peut quand même dériver, parce que son client NTP n'interroge le serveur qu'au démarrage ou trop rarement. Le Site ne s'en remet donc plus au seul NTP de la caméra. À **chaque** vérification (ajout, changement de l'Heure du Site, toutes les heures, « Vérifier maintenant »), il **met à l'heure** chaque Caméra ONVIF active : il lit l'heure en NTP auprès de `temps`, la pousse par `SetSystemDateAndTime` en mode manuel (UTC, fuseau du Site), puis recale la caméra comme en 0.9.0 (`SetNTP` vers l'IP annoncée, mode NTP au fuseau du Site) et relit son Horloge. Une faute sur la mise à l'heure n'arrête pas le calage : l'écart relu décide de l'état.

La **dérive** (avant) et l'**écart** (après) se mesurent contre l'heure servie par `temps` (la source choisie dans l'Heure du Site, ou son repli), plus contre l'horloge de l'OS de `api`. Sans réponse de `temps`, rien n'est poussé ni mesuré : la caméra est recalée et marquée en échec.

L'horloge de l'OS reste hors de portée des conteneurs (toujours pas de `SYS_TIME`). Pour que le repli de `temps` sur l'horloge du serveur reste juste, l'install et la mise à jour Ubuntu réactivent la synchronisation NTP de l'hôte (`timedatectl set-ntp true`) quand elle est coupée.

## Considered Options

- **Pousser l'heure puis recaler, à chaque vérification** (retenu) : l'heure est juste tout de suite, quel que soit le client NTP de la caméra, et la caméra reste tournée vers le Site entre deux vérifications.
- **Recalage forcé seulement** (`SetNTP` + mode NTP renvoyés à chaque fois) : plus léger, mais rien ne garantit qu'une vraie caméra relance une synchronisation sur un réglage identique.
- **Pousser l'heure seulement au-delà de 2 s d'écart** : moins d'appels, mais deux chemins à tester pour un gain nul (la mise à l'heure est idempotente).
- **Mesurer et pousser l'heure de l'OS de `api`** : ignore la source choisie dans l'Heure du Site, et l'ADR 0014 admet que l'OS peut être faux quand la source externe est juste.
- **Faire suivre à l'OS la source externe de l'Heure du Site** : demanderait un pont entre l'API et la configuration de l'hôte, hors de proportion ; la synchronisation par défaut d'Ubuntu suffit au repli.

## Consequences

- Toutes les heures, chaque Caméra ONVIF passe un court instant en mode manuel avant de revenir en NTP.
- Le tableau des Caméras montre la dérive constatée sur l'heure écoulée : une caméra qui ne se synchronise pas seule se voit, même quand elle est « à l'heure ».
- Les états `calée` et `recalée` disparaissent (`à l'heure`, `écart`, `sans ONVIF`, `échec`).
- Sous Mac, rien ne touche l'horloge de l'hôte : Docker Desktop tient l'heure de sa VM depuis macOS.

## Avenant (0.9.1) — fuseau envoyé en décalage du moment

Aux tests humains, une vraie caméra ([`Cam 01`](../cameras/compatibilite.md#cam-01)) était « à l'heure » en UTC mais incrustait une heure de retard : elle ne garde que le décalage du fuseau reçu (`CET-1CEST,M3.5.0,M10.5.0/3` devient `CET-1CEST`, affiché UTC+1), n'applique jamais l'heure d'été, que `DaylightSavings` vaille vrai ou faux, et lit à l'envers un fuseau nommé `UTC` (`UTC-2` affiché UTC−2). Avec un décalage fixe (`CEST-2`), elle affiche juste.

Le Site envoie donc aux Caméras le **décalage horaire du moment** de son fuseau, sous son abréviation et sans règles d'heure d'été : `CEST-2` en été, `CET-1` en hiver pour `Europe/Paris`, calculé par `zoneinfo` (paquet `tzdata`). Quand l'abréviation n'est pas en lettres (`+01`) ou vaut `UTC` / `GMT`, il la remplace par un nom neutre, `ARGOS` (`ARGOS-1`, `ARGOS0`). `SetSystemDateAndTime` part toujours avec `DaylightSavings=false`, dans la Mise à l'heure comme dans le calage : la valeur lue sur la caméra n'est plus recopiée.

Comme le décalage change deux fois par an, une vérification de toutes les Caméras actives a aussi lieu **à l'instant de chaque changement d'heure** du fuseau du Site, recalculé après chaque changement et à chaque changement de fuseau ; la vérification horaire reste.

Le tableau ne mesurait que l'heure UTC : il ne pouvait pas voir une date incrustée fausse. Une Caméra n'est plus « à l'heure » que si son écart relu ne dépasse pas 2 s **et** si le décalage de son fuseau POSIX relu (le décalage de l'heure normale, règles et nom d'heure d'été ignorés, comme le fait la caméra) est celui envoyé ; sinon elle est « écart », et le journal dit quel fuseau elle a relu.

### Considered Options

- **Décalage du moment, sans règles** (retenu) : marche sur une caméra qui sait appliquer l'heure d'été comme sur une qui ne sait pas ; le prix est une vérification de plus, deux fois par an.
- **Règles d'heure d'été POSIX** (0.9.0) : justes sur le papier, fausses sur `Cam 01`, et rien ne dit à l'avance si une caméra les applique.
- **`DaylightSavings=true` avec le fuseau d'hiver** : sans effet sur `Cam 01`, et sa signification varie d'une caméra à l'autre.
- **Liste de caméras connues, chacune son format** : à tenir à jour sans fin ; la [liste des caméras qualifiées](../cameras/compatibilite.md) dit seulement ce qui a été vérifié.

### Consequences

- Entre l'instant du changement d'heure et la fin de la vérification, une Caméra garde l'ancien décalage quelques secondes.
- Un Site arrêté pendant un changement d'heure le reprend à son redémarrage (vérification horaire au démarrage).
- Le fuseau relu en ONVIF montre le décalage du moment (`CEST-2`) ; le Site le reconnaît et affiche le nom du fuseau (`Europe/Paris`).

## Second avenant (0.9.1) — base des fuseaux de l'hôte d'abord

Aux tests humains (Caméra simulée 5), `Africa/Casablanca` incrustait une heure d'avance : le Maroc a changé ses règles en 2026, la base IANA 2026e de l'hôte (macOS, Ubuntu à jour) le met à UTC+0, le paquet Python `tzdata` 2026.4 figé dans l'image à UTC+1. Le Site envoyait le décalage de sa propre base et se comparait à elle : il se disait « à l'heure » avec une heure d'erreur. L'image mélangeait en plus deux bases (`zoneinfo` lisait le `tzdata` de Debian figé à la construction de l'image, la chaîne POSIX venait du paquet Python).

`api` prend donc ses règles dans la **base des fuseaux de l'hôte** : `/usr/share/zoneinfo` est monté en lecture seule (`/usr/share/zoneinfo-hote`), et `zoneinfo` comme la liste des fuseaux le lisent d'abord. Un hôte sans base (dossier absent, créé vide par Docker, ou sans version lisible) donne le paquet `tzdata` embarqué, tenu à sa dernière version ; la base Debian de l'image n'est jamais lue. La version (`+VERSION`, sinon l'en-tête de `tzdata.zi`) est relue à chaque vérification et à chaque pas de la vérification au changement d'heure : une base mise à jour par l'OS vide les caches et donne le nouveau décalage, et le nouvel instant du prochain changement d'heure, sans redémarrage. `GET /api/heure-du-site` et la page Heure du Site disent quelle base sert (version, serveur ou embarquée).

### Considered Options

- **Base de l'hôte d'abord, embarquée en secours** (retenu) : Ubuntu publie la base IANA par ses correctifs de sécurité (`unattended-upgrades`), un pays qui change ses règles est suivi sans release d'ArgOS.
- **Paquet `tzdata` embarqué seul, monté à chaque release** : le retard revient à chaque changement de règles dans le monde, jusqu'à la release et à la mise à jour du Site.
- **Fuseau fixe saisi par l'Administrateur** (décalage à la main) : juste, mais à changer à la main deux fois par an, ce que l'avenant précédent a voulu éviter.

### Consequences

- Un Site Ubuntu suit sa base `tzdata` : l'OS doit garder le paquet `tzdata` installé et à jour (c'est le cas par défaut).
- Sous Mac, Docker Desktop monte la base de macOS : le Site suit les mises à jour de macOS.
- La date incrustée par une caméra peut suivre une base plus récente que celle d'ArgOS, jamais l'inverse sur un Site à jour.
