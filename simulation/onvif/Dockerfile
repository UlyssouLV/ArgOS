FROM python:3.13.13-slim

WORKDIR /app
# Bibliothèque standard seulement : rien à installer, un seul fichier exécuté (openssl, déjà dans l'image, crée
# le certificat HTTPS).
COPY camera_onvif.py ./

# Sans root : les ports 80 et 443 restent ouverts, Docker autorisant les ports bas dans le réseau d'un conteneur.
# /certificat : volume du certificat HTTPS, à l'utilisateur du service pour qu'il l'y crée au premier démarrage ;
# /horloge : volume de la date incrustée dans le Flux (ONVIF_FICHIER_DATE), qu'il y réécrit sans cesse.
RUN useradd --system --no-create-home argos && mkdir /certificat /horloge && chown argos /certificat /horloge
USER argos

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --start-interval=1s \
  CMD ["python", "camera_onvif.py", "sonde"]
CMD ["python", "-u", "camera_onvif.py"]
