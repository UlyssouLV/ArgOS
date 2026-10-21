# AGENTS.md

## Cycle

**« Ouvre la version »** → implement each `ready-for-agent` child (close when tests are green) → **`/code-review`** → **`/ps`** (quality gate, then **`/cqg`** if needed, publish `:staging`) → human tests (`/th` on `:staging`) → **« Finalise la version »** (release + squash; re-read the gate only if `HEAD` moved). The **parent** spec closes via `Fixes` on the squash. Do **not** leave implemented children Open. Do **not** close the parent from `encadrer-implement`.

- **« Initialise le repo »** (`/init`): skill `initialise-le-repo` (already done in this repo). Optional prompts: Sonar, suivi HTML, Docusaurus + GitHub Pages.
- Upgrade an existing install: `/up` (`mettre-a-jour-le-pack`). Sync-only: `update-from-pack.sh` (`--with-docs` / `--with-suivi`)
- **« Augmente la feuille de route de dev »** (`/afr`): skill `augmenter-la-feuille-de-route-dev`
- **« Ouvre la version »** (must include **`X.Y.Z`**): skill `ouvrir-la-version`
- Child-ticket TDD: `/implement`, then skill `encadrer-implement`
- After review: **`/ps`** (`preparer-staging`) — gate + publish `:staging`
- Human tests: `/th` (`tests-humains`) on images `:staging`, after `/ps`
- **« Finalise la version »**: skill `finaliser-la-version`

See `agents/README.md`.

## Tracker

Issues live as GitHub issues in this repo, managed via the `gh` CLI. See `agents/issue-tracker.md`. Infer the repo from `git remote`.

Canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `agents/triage-labels.md`. No `awaiting-merge`.

## Domain

See `agents/domain.md`. File roles and path lookup: `agents/roles.yml`. `/code-review` **Standards**: start here (`AGENTS.md`).

## Tests

Tests: `/t`. Quality gate: `/qg` (`-w` waits up to 15 min until the Sonar PR or branch list shows this HEAD; no poll if credentials are missing; never the default `main` gate). Both: `/vf` / « Vérifie la fiabilité du code ». Fix a red gate: `/cqg`. `encadrer-implement` closes the child after the push and does not wait for Sonar. After an accepted `/code-review`, **`/ps`** runs `/qg -w` (then `/cqg` if needed) and publishes `:staging` before `/th`. `finaliser-la-version` re-runs `/qg -w` only if `HEAD` moved since that green gate (e.g. docs commit).

## Git

Commit and push only when the **current user message** explicitly asks, **except** skill `encadrer-implement` after green tests, skill `commit` (`/c`; `/c -p` pushes; `/c -p -f` after **oui**), skill `initialise-le-repo` (`/init`: `/c -a -p` on `main` is allowed, once), skill `ouvrir-pr` (`/opr`), skill `creer-release` (`/crel`), and skill `fusionner-pr` (`/mpr`). Never force-push otherwise. Never commit `.env`, `*.db`, `.venv`, or secrets.
