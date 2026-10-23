#!/usr/bin/env bash
# Équivalent de `/t -a` pour un runner CI ou une reproduction locale : `.env` d'exemple,
# stack Docker avec Caméras simulées, pytest sur chaque racine `test-roots`.
# Usage : bash scripts/lancer-les-tests.sh [--depuis-registre] [racine ...]
# Sans racine : toutes les racines de agents/roles.yml.
# --depuis-registre : pull + up sans --build (ARGOS_VERSION déjà exporté, ex. ci-<sha>).
set -euo pipefail

DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPOT"

COMPTE="administrateur"
PHRASE="argos-dev-phrase-de-passe-de-test"
DEPUIS_REGISTRE=0
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--depuis-registre" ]]; then
        DEPUIS_REGISTRE=1
    else
        ARGS+=("$arg")
    fi
done

ecrire_env() {
    local cle="$1" valeur="$2" tmp
    tmp="$(mktemp)"
    awk -v cle="$cle" -v valeur="$valeur" '
        index($0, cle "=") == 1 { print cle "=" valeur; vu = 1; next }
        { print }
        END { if (!vu) print cle "=" valeur }
    ' .env > "$tmp" && mv "$tmp" .env
}

TOUTES=()
while IFS= read -r racine; do
    [[ -z "$racine" ]] && continue
    TOUTES+=("$racine")
done < <(python3 "$DEPOT/scripts/lire_test_roots.py")

if [[ ${#ARGS[@]} -eq 0 ]]; then
    RACINES=("${TOUTES[@]}")
else
    RACINES=()
    for demande in "${ARGS[@]}"; do
        trouve=0
        for connue in "${TOUTES[@]}"; do
            if [[ "$demande" == "$connue" ]]; then
                trouve=1
                break
            fi
        done
        if [[ "$trouve" -ne 1 ]]; then
            echo "Racine inconnue ou absente de test-roots : ${demande}" >&2
            echo "Racines connues :" >&2
            printf '  %s\n' "${TOUTES[@]}" >&2
            exit 1
        fi
        RACINES+=("$demande")
    done
fi

if [[ ${#RACINES[@]} -eq 0 ]]; then
    echo "Aucune racine de tests à lancer." >&2
    exit 1
fi

cp .env.example .env
ecrire_env ARGOS_IDENTIFIANT "$COMPTE"
ecrire_env ARGOS_MOT_DE_PASSE "$PHRASE"

COMPOSE=(docker compose -f compose.yaml -f compose.simulation.yaml)

if [[ "$DEPUIS_REGISTRE" -eq 1 ]]; then
    if [[ -z "${ARGOS_VERSION:-}" ]]; then
        echo "ARGOS_VERSION requis avec --depuis-registre (ex. ci-<sha>)." >&2
        exit 1
    fi
    ecrire_env ARGOS_VERSION "$ARGOS_VERSION"
    "${COMPOSE[@]}" pull
    "${COMPOSE[@]}" up -d --wait
else
    "${COMPOSE[@]}" up -d --build --wait
fi

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf --proto '=https' --proto-redir '=https' --tlsv1.2 \
        https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
fi

for racine in "${RACINES[@]}"; do
    [[ -z "$racine" ]] && continue
    echo "=== pytest ${racine} ==="
    (
        cd "$racine"
        uv sync --no-build
        if grep -q pytest-playwright pyproject.toml 2>/dev/null; then
            if [[ "$(uname -s)" == Linux ]]; then
                .venv/bin/playwright install --with-deps chromium
            else
                .venv/bin/playwright install chromium
            fi
        fi
        .venv/bin/python -m pytest
    )
done
