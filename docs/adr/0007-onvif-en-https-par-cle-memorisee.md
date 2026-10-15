# ONVIF en HTTPS par clé mémorisée au premier contact, repli HTTP consenti

Depuis la 0.6.3, le Site règle une Caméra en ONVIF **chiffré** quand son Appareil le propose : il essaie HTTPS sur `443` avant HTTP, et mémorise au premier contact l'empreinte SHA-256 de la **clé publique** (SPKI) du certificat présenté, le **Certificat de l'Appareil**. Il ne vérifie ni l'autorité, ni le nom, ni l'expiration. Toute autre clé est ensuite refusée jusqu'à ce que l'Administrateur fasse confiance à la nouvelle. Une Caméra déjà jointe en HTTPS n'est jamais réglée en HTTP. Une caméra qui ne propose pas HTTPS n'est réglée en HTTP (**ONVIF en clair**) qu'après l'accord de l'Administrateur, une fois par Caméra. TLS 1.0 et 1.1 restent acceptés vers les caméras. Complète l'[ADR 0005](0005-https-par-une-origine-unique-et-une-autorite-du-site.md), qui ne couvre que le côté des postes.

## Considered Options

- **Valider par une autorité** (comme un navigateur) : les caméras présentent des certificats auto-signés, adressés par IP ; presque aucune ne passerait, et toutes retomberaient en HTTP. Installer un certificat signé par l'Autorité du Site sur chaque caméra demanderait une API que la plupart n'ont pas.
- **Accepter tout certificat** : chiffre contre l'écoute, mais un appareil qui s'intercale présente son propre certificat et reçoit l'empreinte du mot de passe, comme en HTTP.
- **Accepter seul une nouvelle clé** (l'Administrateur n'a rien à faire) : revient à accepter tout certificat ; rien ne distingue une remise en usine d'un usurpateur (la MAC se falsifie).
- **Empreinte du certificat entier** plutôt que de la clé : une caméra qui renouvelle son certificat expiré avec la même clé déclencherait une fausse alerte.
- **Repli HTTP automatique et signalé** : ArgOS enverrait en clair sans que personne l'ait voulu, y compris après la disparition d'un HTTPS filtré par un attaquant (rétrogradation).
- **Pas de Réglages sans HTTPS** : priverait de Réglages beaucoup de caméras d'entrée de gamme.
- **TLS 1.2 minimum** : les caméras qui n'ont que TLS 1.0 retomberaient en HTTP, ce qui est pire qu'un TLS ancien avec une clé mémorisée.

## Consequences

- Le premier contact est le point faible (TOFU) : il a lieu à la première ouverture des Réglages, Administrateur présent, et l'empreinte mémorisée est affichée.
- Une clé changée (remise en usine, nouveau firmware, autre appareil) bloque les Réglages de cette Caméra jusqu'à un clic de l'Administrateur ; le Live, l'état et le reste n'en dépendent pas.
- Les adresses de service annoncées par la caméra (`XAddr`) ne servent que pour leur chemin : schéma, hôte et port sont ceux du contact retenu, pour qu'aucune requête ne reparte en HTTP.
- Port, schéma, clé et accord suivent l'hôte de la Caméra : gardés au changement d'IP par la MAC, effacés quand l'Administrateur change l'hôte.
- L'empreinte WS-Security (SHA-1, imposé par la norme) ne circule en clair que pour une Caméra en ONVIF en clair ; un mot de passe court y est signalé. La vraie défense de ces caméras reste l'isolement du réseau des caméras.
