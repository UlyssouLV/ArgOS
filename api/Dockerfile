FROM python:3.13.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
# Roues seulement : aucun script de construction d'une dépendance ne s'exécute à l'image.
RUN uv sync --frozen --no-dev --no-build
# Seulement ce que l'API exécute : rien d'autre du dossier (secrets, venv locale) n'entre dans l'image.
COPY alembic.ini ./
COPY migrations ./migrations
COPY argos_api ./argos_api

# Sans root : l'API ne fait que des connexions sortantes et lit /proc/net/arp, lisible par tous.
RUN useradd --system --no-create-home argos
USER argos

EXPOSE 8000
# Migrations d'abord : un clone neuf démarre sans étape manuelle.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn argos_api.app:creer_app --factory --host 0.0.0.0 --port 8000"]
