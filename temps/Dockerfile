# Serveur de temps du Site : NTP (UDP 123) sur le réseau des caméras (docs/adr/0014-serveur-de-temps-du-site.md).
FROM alpine:3.22.2
RUN apk add --no-cache chrony
COPY lancer.sh /usr/local/bin/lancer.sh
EXPOSE 123/udp
# chronyc -n tracking : par la socket locale, seule voie de commande (cmdport 0), en utilisateur chrony
# (le conteneur n'a pas DAC_OVERRIDE pour /run/chrony).
HEALTHCHECK --interval=2s --timeout=5s --retries=30 CMD ["su", "-s", "/bin/sh", "chrony", "-c", "chronyc -n tracking"]
ENTRYPOINT ["/bin/sh", "/usr/local/bin/lancer.sh"]
