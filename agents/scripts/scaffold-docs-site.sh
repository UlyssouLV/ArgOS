#!/bin/bash
# Scaffold or refresh the generic Docusaurus docs-site in a target repo.
# Usage (from pack or via PATH):
#   scaffold-docs-site.sh <TARGET_REPO_ROOT> [--force-owned]
# --force-owned : when docs-site already exists, overwrite PACK_OWNED.txt paths only
# Without existing docs-site: full copy + stubs + workflow + roles.yml role.
set -euo pipefail

TARGET="${1:-}"
MODE_FORCE_OWNED=0
shift || true
for arg in "$@"; do
  case "$arg" in
    --force-owned) MODE_FORCE_OWNED=1 ;;
    *)
      echo "Option inconnue : $arg" >&2
      exit 1
      ;;
  esac
done

if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
  echo "Usage: $0 <TARGET_REPO_ROOT> [--force-owned]" >&2
  exit 1
fi

PACK="$(cd "$(dirname "$0")/../.." && pwd)"
TMPL="$PACK/agents/templates/docs-site"
STUBS="$PACK/agents/templates/docs-stubs"
WF_SRC="$PACK/agents/templates/github/workflows/deploy-docs.yml"

if [ ! -d "$TMPL" ] || [ ! -f "$TMPL/package.json" ]; then
  echo "Template introuvable : $TMPL" >&2
  exit 1
fi

# Resolve owner/repo from git remote
OWNER="OWNER"
REPO="REPO"
TITLE="Documentation"
TAGLINE="Documentation du projet — produit, features et décisions"
if git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  remote="$(git -C "$TARGET" remote get-url origin 2>/dev/null || true)"
  if [[ "$remote" =~ github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
  fi
  # Prefer README H1 or package name later — default to repo name
  TITLE="$REPO"
fi

apply_placeholders() {
  local file="$1"
  if [ ! -f "$file" ]; then
    return
  fi
  OWNER="$OWNER" REPO="$REPO" TITLE="$TITLE" TAGLINE="$TAGLINE" python3 - "$file" <<'PY'
import os, sys
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
for key in ("OWNER", "REPO", "TITLE", "TAGLINE"):
    text = text.replace(f"__{key}__", os.environ[key])
path.write_text(text)
PY
}

add_docs_site_role() {
  local roles="$TARGET/agents/roles.yml"
  if [ ! -f "$roles" ]; then
    echo "avertissement : agents/roles.yml absent — rôle docs-site non ajouté" >&2
    return
  fi
  if grep -q 'docs-site:' "$roles"; then
    return
  fi
  python3 - "$roles" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
block = """  docs-site:
    paths:
      - docs-site/
"""
if "docs-site:" in text:
    raise SystemExit(0)
lines = text.splitlines(keepends=True)
out = []
i = 0
inserted = False
while i < len(lines):
    out.append(lines[i])
    if not inserted and lines[i].startswith("  roadmap:"):
        i += 1
        while i < len(lines) and (lines[i].startswith("    ") or lines[i].strip() == ""):
            out.append(lines[i])
            i += 1
        out.append(block if block.endswith("\n") else block + "\n")
        inserted = True
        continue
    i += 1
if not inserted:
    out.append(block if block.endswith("\n") else block + "\n")
path.write_text("".join(out))
PY
  echo "ajouté rôle docs-site dans agents/roles.yml"
}

copy_stubs() {
  mkdir -p "$TARGET/docs/changelog" "$TARGET/docs/bugs" "$TARGET/docs/feuille-de-route" "$TARGET/docs/features" "$TARGET/docs/adr"
  for pair in \
    "changelog/README.md:docs/changelog/README.md" \
    "bugs/README.md:docs/bugs/README.md" \
    "feuille-de-route/README.md:docs/feuille-de-route/README.md" \
    "features/index.md:docs/features/index.md"
  do
    src="${pair%%:*}"
    dest="${pair##*:}"
    if [ ! -f "$TARGET/$dest" ] && [ -f "$STUBS/$src" ]; then
      mkdir -p "$(dirname "$TARGET/$dest")"
      rsync -a "$STUBS/$src" "$TARGET/$dest"
      echo "créé   $dest"
    fi
  done
  if [ ! -f "$TARGET/docs/glossaire.md" ]; then
    printf '%s\n' '# Glossary' > "$TARGET/docs/glossaire.md"
    echo "créé   docs/glossaire.md"
  fi
}

copy_workflow() {
  mkdir -p "$TARGET/.github/workflows"
  if [ ! -f "$TARGET/.github/workflows/deploy-docs.yml" ]; then
    rsync -a "$WF_SRC" "$TARGET/.github/workflows/deploy-docs.yml"
    echo "créé   .github/workflows/deploy-docs.yml"
  elif [ "$MODE_FORCE_OWNED" -eq 1 ]; then
    rsync -a "$WF_SRC" "$TARGET/.github/workflows/deploy-docs.yml"
    echo "MAJ    .github/workflows/deploy-docs.yml"
  fi
}

sync_owned_only() {
  local owned="$TMPL/PACK_OWNED.txt"
  if [ ! -f "$owned" ]; then
    echo "PACK_OWNED.txt introuvable" >&2
    exit 1
  fi
  while IFS= read -r rel || [ -n "$rel" ]; do
    [[ -z "$rel" || "$rel" =~ ^# ]] && continue
    if [ -e "$TMPL/$rel" ]; then
      mkdir -p "$(dirname "$TARGET/docs-site/$rel")"
      rsync -a "$TMPL/$rel" "$TARGET/docs-site/$rel"
      echo "MAJ    docs-site/$rel"
    fi
  done < "$owned"
  # Always refresh workflow when syncing owned
  rsync -a "$WF_SRC" "$TARGET/.github/workflows/deploy-docs.yml"
  echo "MAJ    .github/workflows/deploy-docs.yml"
}

if [ -d "$TARGET/docs-site" ] && [ -f "$TARGET/docs-site/package.json" ]; then
  if [ "$MODE_FORCE_OWNED" -eq 1 ]; then
    echo "docs-site présent — sync chemins PACK_OWNED uniquement"
    sync_owned_only
    add_docs_site_role
    copy_stubs
  else
    echo "docs-site déjà présent — rien (passe --force-owned pour rafraîchir les fichiers pack)"
  fi
  exit 0
fi

echo "Scaffold docs-site → $TARGET (owner=$OWNER repo=$REPO)"
mkdir -p "$TARGET/docs-site"
rsync -a --exclude .DS_Store --exclude node_modules --exclude build --exclude .docusaurus \
  "$TMPL"/ "$TARGET/docs-site/"
apply_placeholders "$TARGET/docs-site/docusaurus.config.ts"
copy_stubs
copy_workflow
add_docs_site_role
echo "docs-site prêt. Activer GitHub Pages (Settings → Pages → GitHub Actions) après le premier push."
