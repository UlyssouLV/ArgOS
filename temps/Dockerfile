# Serveur de temps du Site : NTP (UDP 123) sur le réseau des caméras (docs/adr/0014-serveur-de-temps-du-site.md).
FROM alpine:3.22.2
# Sans root : Docker laisse un utilisateur ouvrir le port 123 dans le réseau du conteneur. chrony écrit sa
# configuration, sa dérive et son pidfile dans /var/lib/argos-temps, sa socket de commande dans /run/chrony.
RUN apk add --no-cache chrony \
    && mkdir -p /var/lib/argos-temps /run/chrony \
    && chown chrony:chrony /var/lib/argos-temps /run/chrony \
    && chmod 750 /run/chrony
COPY lancer.sh /usr/local/bin/lancer.sh
EXPOSE 123/udp
USER chrony
# chronyc -n tracking : par la socket locale, seule voie de commande (cmdport 0).
HEALTHCHECK --interval=2s --timeout=5s --retries=30 CMD ["chronyc", "-n", "tracking"]
ENTRYPOINT ["/bin/sh", "/usr/local/bin/lancer.sh"]
