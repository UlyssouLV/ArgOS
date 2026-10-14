# HTTPS par une origine unique et une Autorité du Site

Le Site n'est servi que par **une seule origine HTTPS** : le nginx du conteneur `web` termine le TLS et relaie l'UI, l'API (`/api`) et le Live (WHEP, HLS) vers les conteneurs ; l'API et MediaMTX ne publient plus leurs ports HTTP. Le certificat du serveur est signé par l'**Autorité du Site**, une autorité de certification générée une fois sur la machine hôte par un service ponctuel `certificats`, que l'Administrateur installe sur chacun de ses postes. Un certificat fourni par l'Administrateur (nom de domaine, VPN) peut la remplacer.

## Considered Options

- **TLS sur chaque service** (uvicorn, `webrtcEncryption` / `hlsEncryption` de MediaMTX, nginx) : pas de proxy, mais quatre origines, CORS avec credentials à garder, le certificat monté partout, et des ports à fermer un par un.
- **Caddy et sa CA interne** (`tls internal`) : génère et renouvelle seul, mais remplace nginx, fait tourner son intermédiaire à son rythme et rend moins net le fichier à distribuer aux postes.
- **Certificat auto-signé** : rien à installer, mais un avertissement sur chaque poste, qui habitue à cliquer sur « continuer » et annule la protection contre l'usurpation.
- **Let's Encrypt seul** : aucun avertissement, mais exige un nom de domaine public et un accès sortant ; contraire au Site autonome sur réseau local. Reste possible comme certificat fourni.

## Consequences

- Chaque poste doit installer l'Autorité du Site une fois ; perdre le volume de l'Autorité oblige à la réinstaller partout.
- Une seule origine : plus de CORS, et le front n'utilise que des URL relatives.
- Le certificat serveur nomme l'IP du Site (`MTX_WEBRTCADDITIONALHOSTS`) : un changement d'IP le régénère au démarrage, sans toucher à l'Autorité.
- La clé de l'Autorité n'est montée que dans `certificats` ; `web`, seul exposé, ne détient que la clé serveur de cette machine (397 jours).
- Le média WebRTC (UDP `8189`) et RTSP (`8554`) restent hors du proxy.
