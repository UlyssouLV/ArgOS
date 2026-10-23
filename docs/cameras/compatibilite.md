# Caméras qualifiées

Une vraie caméra ne fait pas toujours ce qu'ONVIF annonce. Cette page liste les caméras essayées avec ArgOS sur un vrai Site, ce qu'elles font de l'heure que le Site leur envoie, et la procédure pour en qualifier une nouvelle. Une caméra absente de la liste peut très bien marcher : elle n'a simplement pas été vérifiée.

Pour aller plus loin : [Paramétrer une Caméra](parametrer-une-camera.md), [ADR 0015](../adr/0015-mise-a-l-heure-a-chaque-verification.md) (et son avenant sur le fuseau).

## Liste

| Caméra | Marque, modèle, firmware (`GetDeviceInformation`) | Ce qu'elle fait d'un fuseau | Ce qu'Argos lui envoie | Qualifiée |
| --- | --- | --- | --- | --- |
| [`Cam 01`](#cam-01) | `H264`, `IPC_GK7201V200_G3H_S38` (puce Goke, firmware XiongMai) ; version du firmware à relever | Garde le décalage seul, jamais d'heure d'été, `UTC` lu à l'envers | Décalage du moment (`CEST-2` / `CET-1`), `DaylightSavings=false`, ONVIF en HTTP sur `8899` | 0.9.1 |

### Cam 01

La caméra de dev décrite dans [Paramétrer une Caméra](parametrer-une-camera.md#4-ce-qua-montré-la-caméra-de-dev), sur le Site Ubuntu des tests humains de la 0.9.1. Essais ONVIF (`SetSystemDateAndTime` puis `GetSystemDateAndTime`, Paris en heure d'été) :

| Envoyé | Gardé par la caméra | Affiché |
| --- | --- | --- |
| `CET-1CEST,M3.5.0,M10.5.0/3`, `DaylightSavings` faux | `CET-1CEST` | UTC+1 ❌ |
| idem, `DaylightSavings` vrai | `CET-1CEST` | UTC+1 ❌ |
| `CEST-2` | `EET-2EETDST` | UTC+2 ✅ |
| `UTC-2` | `FNT2` | UTC−2 ❌ (sens inversé) |
| `CET-1` | `CET-1CEST` | UTC+1 ✅ (hiver) |

Elle ne garde que le décalage du fuseau (en le renommant à sa façon), n'applique jamais l'heure d'été et inverse le sens d'un fuseau nommé `UTC`. Depuis la 0.9.1, le Site lui envoie le décalage du moment, sans règles ([avenant à l'ADR 0015](../adr/0015-mise-a-l-heure-a-chaque-verification.md#avenant-091--fuseau-envoyé-en-décalage-du-moment)) : sa date incrustée est l'heure locale du Site, été comme hiver, et le Site la recale à chaque changement d'heure. La Caméra simulée 5 l'imite (`ONVIF_FUSEAU_DECALAGE_SEUL`, [simulation ONVIF](../../simulation/onvif/README.md)).

## Qualifier une nouvelle caméra

À faire sur un Site de dev ou de test, la caméra ajoutée dans ArgOS et l'ONVIF joignable (en HTTPS, ou en clair accordé).

1. **Identité** : lire `GetDeviceInformation` (fabricant, modèle, version du firmware) avec le conteneur jetable de [Paramétrer une Caméra](parametrer-une-camera.md#lire-la-caméra), et noter le port ONVIF et le schéma (HTTPS ou HTTP).
2. **Fuseaux** : pour chaque fuseau ci-dessous, l'envoyer en mode manuel (`SetSystemDateAndTime`, `DateTimeType=Manual`, l'heure UTC du moment), relire `GetSystemDateAndTime` (`TZ` gardé, `DaylightSavings`), et comparer la date incrustée dans le Live à l'heure réelle :
   - les règles d'heure d'été (`CET-1CEST,M3.5.0,M10.5.0/3`), avec `DaylightSavings` faux puis vrai ;
   - le décalage du moment (`CEST-2` en été, `CET-1` en hiver) ;
   - un fuseau nommé `UTC` avec un décalage (`UTC-2`) ;
   - un nom neutre (`ARGOS-1`), comme ce que le Site envoie pour une abréviation numérique.
3. **Par ArgOS** : sur la page Heure du Site, choisir tour à tour chacun des fuseaux proposés qui compte pour le Site (au moins `Europe/Paris` et `UTC`), puis « Vérifier maintenant » : la Caméra est « à l'heure » et la date incrustée est l'heure locale du Site. Une Caméra « écart » avec un écart de moins de 2 s a gardé un autre décalage : le journal de l'API dit lequel (`docker compose logs api | grep "en écart"`).
4. **Noter** la caméra dans la liste : marque, modèle, firmware, ce qu'elle fait d'un fuseau, ce qu'Argos lui envoie, et la version d'ArgOS qualifiée. Si elle demande autre chose que le décalage du moment, ouvrir un bug (`/cub`) avec le tableau des essais.
