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
