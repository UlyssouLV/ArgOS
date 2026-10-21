---
name: preparer-staging
description: >-
  After an accepted `/code-review` on the version PR: `/qg -w` (then `/cqg` if
  needed), publish `:staging` from this branch SHA, then hand off to `/th`.
  Use when the user types `/ps`, or says « Prépare le staging », « prepare
  staging ». Not `/th`. Not Finalise. Not `/implement`.
---

# Préparer le staging (`/ps`)

Triggered by **`/ps`** or **« Prépare le staging »**, only after the user accepted a **`/code-review`** of this version branch. Do **not** run `/code-review` here. Do **not** `/th` here. Do **not** merge or tag.

Paths: **`agents/roles.yml`**.

## 0. Locate the PR

Resolve **base** per `agents/docs/integration-channel.md`. Current branch must not be **protected** (`main` / `master` / **base**). Resolve the open PR (`gh pr view`). If none: **stop**. Infer **`X.Y.Z`** from the branch or PR title. If missing: ask and wait.

If the user has not clearly accepted the review this turn: ask whether `/code-review` is accepted and **wait** for **oui**. Anything else → stop.

## 1. Implementation children Closed; human-test still Open

List children of the parent. Every **`ready-for-agent`** (and other implementation) child in scope must be **Closed**. The **`Tests humains — VX.Y.Z`** child must still be **Open** (label `ready-for-human`). Otherwise **stop** and say what is wrong (too early, or `/th` already done → Finalise).

## 2. Quality gate

Load `.env` the same way **`quality-gate`** does. If any of that skill’s three `SONAR_*` keys is missing or empty → one line that Sonar is skipped; go to step 3. Do not `/qg`. Do not `/cqg`.

Otherwise run **`quality-gate`** as if **`/qg -w`**.

- No analysis for `HEAD` after the wait → **stop**.
- **`OK`** → continue.
- Not **`OK`** → run **`corriger-quality-gate`** as if **`/cqg`**.
  - Stopped without a code change → **stop**.
  - Working tree dirty → run **`/t`** (fail → **stop**). Stage those files and **`commit`** as if **`/c -p`**. Then **`/qg -w`** once. Not **`OK`** → **stop**.

## 3. Publish `:staging` from this branch

From the **repo root**, current branch:

```bash
gh workflow run "Publier images staging" --ref "$(git branch --show-current)"
```

Then wait until that run completes successfully on this ref (`gh run list --workflow "Publier images staging" --branch …`, then `gh run watch`). Failure → **stop**. Do not invent another publish path.

Do **not** push `:staging` from `main` here. This SHA is the early-access digest for `/th`.

## 4. Hand off

Tell the user in French (adapt `#n` / `X.Y.Z`):

1. `:staging` is the digest of this PR `HEAD` — pull with `ARGOS_VERSION=staging` (compose / Site de test).
2. Play the plan on the open **`Tests humains — VX.Y.Z`** ticket (`#n`).
3. When done, launch **`/th`** with the results. Do **not** Finalise until `#n` is Closed.

## Not this skill

- Review vs `main` → human types `/code-review`
- Human-test results → `tests-humains` (`/th`)
- Release / squash → `finaliser-la-version`
- Gate only → `quality-gate` (`/qg`)
- Fix gate only → `corriger-quality-gate` (`/cqg`)
- Child wrap → `encadrer-implement`
