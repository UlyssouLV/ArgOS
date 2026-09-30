# ArgOS

Plateforme de **vidéosurveillance IP auto-hébergée**, conçue pour rester générique et multi-marques : caméras RTSP/ONVIF, enregistrement, live, événements, puis détection et PTZ au fil des versions.

Le nom évoque à la fois le chien d’Ulysse et Argos Panoptès (la vigilance à plusieurs yeux). Le projet est né d’un besoin de surveillance locale sur une grande propriété ; l’objectif logiciel est un produit self-hosted, sans dépendance cloud propriétaire.

## Principes

- Standards ouverts (RTSP, ONVIF, H.264/H.265, Docker)
- Caméras abstraites (réelles ou simulées via MediaMTX) — pas de lock-in fabricant
- Modularité : chaque brique testable ; IA, ONVIF, PTZ optionnels
- PostgreSQL pour les données ; UI web React (navigateur / kiosque) prévue
- Intent open source pendant le développement (licence formelle à la première release)

## État actuel

Initialisation du dépôt (pack agents, docs, cadrage). Pas encore de stack applicative runnable.

Prochaines étapes prévues :

1. Rédiger / enrichir la [feuille de route de dev](docs/dev/feuille-de-route-dev.md)
2. Ouvrir des versions (`Ouvre la version`) et livrer les briques pas à pas
3. Composer progressivement `argos-backend`, `argos-frontend`, Postgres, MediaMTX (puis workers vidéo / IA selon besoin)

Hypothèses et notes de conception du moment (non figées) : [docs/specs/contexte-initial.md](docs/specs/contexte-initial.md).

## Développement avec les agents

Voir [AGENTS.md](AGENTS.md) pour le cycle **Ouvre la version → implement → Finalise la version**, les tests (`/t`) et le quality gate (`/qg`).

## Licence

À définir à la première release. Développement mené dans un esprit open source.
