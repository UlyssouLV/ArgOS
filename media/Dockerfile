# Pont : MediaMTX officiel, configuration du Site cuite dans l'image (docs/adr/0001-mediamtx-en-pont.md).
FROM bluenviron/mediamtx:1.21.1
COPY --chown=65532:65532 mediamtx.yml /mediamtx.yml
COPY --chown=65532:65532 enregistrements/.keep /enregistrements/.keep
USER 65532
