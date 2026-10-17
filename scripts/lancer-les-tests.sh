#!/usr/bin/env bash
# Équivalent de `/t -a` pour un runner CI ou une reproduction locale : `.env` d'exemple,
# stack Docker avec Caméras simulées, pytest sur chaque racine `test-roots`.
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPOT"

COMPTE="administrateur"
PHRASE="argos-dev-phrase-de-passe-de-test"

ecrire_env() {
    local cle="$1" valeur="$2" tmp
    tmp="$(mktemp)"
    awk -v cle="$cle" -v valeur="$valeur" '
        index($0, cle "=") == 1 { print cle "=" valeur; vu = 1; next }
        { print }
        END { if (!vu) print cle "=" valeur }
    ' .env > "$tmp" && mv "$tmp" .env
}

cp .env.example .env
ecrire_env ARGOS_IDENTIFIANT "$COMPTE"
ecrire_env ARGOS_MOT_DE_PASSE "$PHRASE"

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
fi

docker compose -f compose.yaml -f compose.simulation.yaml up -d --build --wait

racines() {
    python3 <<'PY'
from pathlib import Path

dans_test_roots = False
dans_paths = False
for ligne in Path("agents/roles.yml").read_text().splitlines():
    if ligne.startswith("  test-roots:"):
        dans_test_roots = True
        continue
    if dans_test_roots and ligne.startswith("    paths:"):
        dans_paths = True
        continue
    if dans_paths:
        if ligne.startswith("      - "):
            print(ligne[8:].strip().strip("'\""))
        elif ligne.strip() and not ligne.startswith("      "):
            break
PY
}

while IFS= read -r racine; do
    [ -z "$racine" ] && continue
    echo "=== pytest ${racine} ==="
    (
        cd "$racine"
        uv sync
        if grep -q pytest-playwright pyproject.toml 2>/dev/null; then
            if [ "$(uname -s)" = Linux ]; then
                .venv/bin/playwright install --with-deps chromium
            else
                .venv/bin/playwright install chromium
            fi
        fi
        .venv/bin/python -m pytest
    )
done < <(racines)
