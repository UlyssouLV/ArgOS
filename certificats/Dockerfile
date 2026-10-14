# Service ponctuel : crée l'Autorité du Site et le certificat serveur, puis s'arrête (docs/adr/0005-…).
FROM alpine:3.22.2
# Points de montage de ses deux volumes, à l'utilisateur du service : un volume neuf en prend la propriété.
RUN apk add --no-cache openssl \
  && mkdir -p /autorite /certificats-serveur \
  && chown 101:101 /autorite /certificats-serveur
COPY generer.sh /usr/local/bin/generer.sh
# Utilisateur de nginx dans l'image de web (nginx-unprivileged) : la clé du serveur est à lui sans root ni chown.
USER 101:101
ENTRYPOINT ["/bin/sh", "/usr/local/bin/generer.sh"]
