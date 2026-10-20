# macvlan sur la prise des caméras : l'API lit les adresses MAC

Remplace en partie l'[ADR 0002](0002-detection-depuis-le-reseau-bridge.md) : les sous-réseaux restent déclarés par le script hôte, mais l'API ne se contente plus du réseau bridge. Pour reconnaître un Appareil par son adresse MAC (0.4.2), `api` gagne, en prod Linux, une interface **macvlan** par prise des caméras, avec une IP fixe proposée par le script hôte hors DHCP. L'API y parle aux caméras sans NAT : après chaque sonde, sa propre table de voisinage donne la MAC de l'IP sondée. Elle garde le bridge pour les noms Compose et les ports publiés, et n'accepte aucune requête arrivée par le réseau des caméras. Le réseau macvlan vit dans `compose.reseau-cameras.yaml`, ajouté à `COMPOSE_FILE` par le script sur Linux seulement.

**Complété par l'[ADR 0014](0014-serveur-de-temps-du-site.md) (0.9.0, #133).** Le réseau des caméras n'est plus « une sortie seulement » : le service `temps` y sert l'heure en NTP (UDP 123, et rien d'autre) à une seconde IP fixe hors DHCP. `api` n'y sert toujours rien.

## Considered Options

- **Table ARP de l'hôte montée dans `api`** (`/proc/net/arp`) : une ligne de Compose, mais un fichier procfs lié à un processus de l'hôte, fragile, et Linux seulement.
- **Service sur l'hôte qui expose la table ARP** : marcherait aussi sur Mac, mais ajoute un composant hors Docker à démarrer, sécuriser et tester.
- **ONVIF (`GetNetworkInterfaces`)** : demande souvent les identifiants de la caméra, et ONVIF est hors périmètre.
- **`network_mode: host`** : déjà écarté par l'ADR 0002.

## Consequences

- En dev, les Caméras simulées partagent déjà un réseau Compose avec `api` : même mécanisme (table de voisinage du conteneur), MAC fixes, testable sans macvlan.
- Sous Docker Desktop (Mac), macvlan n'existe pas : les vraies caméras n'ont pas de MAC, et ArgOS garde pour elles le comportement de la 0.4.1. Derrière un routeur non plus.
- ArgOS occupe une IP de plus sur le réseau des caméras, à garder hors de la plage DHCP.
