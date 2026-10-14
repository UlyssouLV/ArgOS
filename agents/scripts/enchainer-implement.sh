#!/bin/bash
# Ouvre une nouvelle session Claude Code sur /implement #<n>, hors du terminal courant.
# Usage (depuis la racine du repo) : bash agents/scripts/enchainer-implement.sh <n>
# macOS + Terminal.app. Ne remplace pas /implement dans Cursor Agent chat.
set -euo pipefail

N="${1:-}"
if ! [[ "$N" =~ ^[0-9]+$ ]]; then
  echo "Usage: $0 <numéro-issue-enfant>" >&2
  exit 1
fi

REPO="$(pwd)"
if [ ! -d "$REPO/agents/skills" ]; then
  echo "À lancer à la racine d’un repo agents (agents/skills/ introuvable)." >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "claude introuvable dans le PATH." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) ;;
  *)
    echo "Enchaînement auto : macOS seulement pour l’instant (Terminal.app)." >&2
    exit 1
    ;;
esac

# Nouvelle fenêtre Terminal.app, session Claude fraîche (= effet /clear).
osascript \
  -e 'on run argv' \
  -e 'set repo to item 1 of argv' \
  -e 'set n to item 2 of argv' \
  -e 'set cmd to "cd " & quoted form of repo & " && exec claude \"/implement #" & n & "\""' \
  -e 'tell application "Terminal"' \
  -e '  activate' \
  -e '  do script cmd' \
  -e 'end tell' \
  -e 'end run' \
  -- "$REPO" "$N"

echo "Session Claude ouverte : /implement #$N"
