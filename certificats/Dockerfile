# Service ponctuel : crée l'Autorité du Site et le certificat serveur, puis s'arrête (docs/adr/0005-…).
FROM alpine:3.22.2
RUN apk add --no-cache openssl
COPY generer.sh /usr/local/bin/generer.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/generer.sh"]
