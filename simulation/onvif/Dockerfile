FROM python:3.13.13-slim

WORKDIR /app
# Bibliothèque standard seulement : rien à installer, un seul fichier exécuté.
COPY camera_onvif.py ./

# Sans root : le port 80 reste ouvert, Docker autorisant les ports bas dans le réseau d'un conteneur.
RUN useradd --system --no-create-home argos
USER argos

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --start-interval=1s \
  CMD ["python", "camera_onvif.py", "sonde"]
CMD ["python", "-u", "camera_onvif.py"]
