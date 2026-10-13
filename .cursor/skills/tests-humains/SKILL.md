---
name: tests-humains
description: >-
  Record human-test results for the version’s ready-for-human child, optionally
  verify the report and capture screenshots on request, commit images, update
  the issue body, and close it. Use when the user types `/th`, says « tests
  humains », or reports which scenarios they ran after the plan from
  encadrer-implement. Not `/implement`. Not `/cci`.
---

# Tests humains (`/th`)

Triggered by **`/th`** or when the user reports human-test results for the current version (after `encadrer-implement` proposed the plan). This path **is** permission to edit and close the **human-test child** only, and to commit screenshots via skill **`commit`** when captures exist.

Paths: **`agents/roles.yml`**. Ticket shape: **`agents/issue-tracker.md`** (*Human-test child*).

`/` = this skill’s trigger. Treat `/th` as a whole token. Optional intent in the same message (French or English), whole words:

- **captures** / **preuves** / **screenshots** / **avec captures** → after a successful verify, produce and commit screenshots (step 4).
- Absent → never invent captures; images already attached in the chat still count (step 4).

## 1. Find the ticket

Infer **`X.Y.Z`** from the branch `vX.Y.Z-<slug>` or the open PR title. If missing: ask and **wait**.

Find the open child titled **`Tests humains — VX.Y.Z`** with label **`ready-for-human`** (parent via `Part of`). If none Open: say so and stop. If several: ask which `#n` and wait.

## 2. Read the human report

From the **current user message** (and images attached in this chat):

- Which plan scenarios were **played** (pass / fail / notes) — keep the human’s wording precise
- Which were **not played** (short reason OK)
- Product bullets for **Ce qu’on peut faire maintenant** if the human stated them; otherwise draft them from the played scenarios + parent spec (product language)

Partial plans are OK. Do not invent failures the human did not report.

If the message has no results at all: ask what they ran and **wait**. Do not close. Do not verify. Do not capture.

## 3. Verify the report

Goal: check that what the human described is **still true** on the running product (or stop with a clear gap). This is **not** a substitute for the human judgment — it corroborates the récit.

1. From the played scenarios + notes, list **observable checks** (UI state, API response, visible text, video playing, …). Prefer the version’s plan, parent spec, and existing `tests/web/` (pytest-playwright) patterns when they map cleanly.
2. Run those checks against the local stack when it is up (or say what must be running and **wait** if it is not). Reuse Playwright / pytest-playwright when a short scripted check is enough; do not invent a parallel e2e suite for every `/th`.
3. Compare outcomes to the human report:
   - **OK** — checks match the récit (or the gaps are only non-observable / environment limits you stated).
   - **Écart** — at least one check contradicts the report, or a claimed scenario cannot be corroborated.

On **Écart**: write the mismatches in French, **do not** close the ticket, **do not** take captures. Ask the human what to do (correct the report, re-test, or accept a documented limit) and **wait**.

On **OK**: continue. Note in **Résultats** that the report was verified (what was checked, briefly).

Skip heavy automation when the report is text-only and the claims are not UI/API-checkable in this repo without new tooling — then say so in one line (« non vérifié automatiquement : … ») and continue only if the human did not demand captures that need that check. If they asked for **captures** but verification cannot run: **wait** (ask to start the stack or drop the capture request).

## 4. Screenshots

Two sources of images (either is enough):

**A. Chat attachments** — if the human attached evidence images, save them under **`docs/img/changelog/vX.Y.Z/`** (create the folder). Filenames: short kebab ASCII (`scenario-1.png`, …).

**B. On request after verify OK** — only if step 3 was **OK** **and** the user asked for captures / preuves / screenshots in this turn:

1. For each played **pass** scenario worth illustrating, drive the UI (Playwright / pytest-playwright against the same stack) to the state described and capture the relevant viewport or element.
2. Write files under **`docs/img/changelog/vX.Y.Z/`** with short kebab names tied to the scenario.
3. Do **not** capture failed scenarios or scenarios the human marked non-joué.

If neither A nor B applies → skip. Text-only results are enough to close when verify is OK (or explicitly non-applicable).

When any new files were written under that folder: run skill **`commit`** as if the user had typed **`/c -a -p`** (message about preuves / changelog images for this version).

## 5. Update the issue body

`gh issue edit <n> --body` with the full *Human-test child* shape:

- Keep `Part of`, What to build, Acceptance criteria (check off what is done), Blocked by
- **`## Plan de tests`**: same scenarios; checkboxes reflect played / left unchecked or annotated as non-joué
- **`## Résultats`**: what was played, outcomes, non-joués ; plus a short **Vérification** line (OK / écart / non vérifié automatiquement)
- **`## Ce qu’on peut faire maintenant`**: product bullets; for each screenshot, a Markdown image pointing at the repo path (e.g. `![…](../../img/changelog/vX.Y.Z/….png)` relative to a future `docs/changelog/…` page, or the same style as other `docs/img/` references in this repo)

## 6. Close

Only after step 3 is **OK** (or explicitly non-applicable without a capture request), and the body is updated:

1. `gh issue edit <n> --remove-label "ready-for-human"` (absent → continue)
2. `gh issue close <n>` with comment: `Tests humains documentés sur <branch> (<sha>).`

Do **not** use `/cci`. Do not close the parent. Do not `/implement`.

## 7. Hand off

Tell the user in French: ticket `#n` Closed; next **`/code-review`**, then **Finalise la version** if the review is accepted. Mention whether captures were committed or skipped.

## Not this skill

- Propose the plan after the last implement → `encadrer-implement`
- Close an implementation child → `fermer-ticket-enfant` (`/cci`)
- Release / squash → `finaliser-la-version`
- Commit only → `commit` (`/c`)
- Invent a full e2e suite for every version → out of scope; prefer existing `tests/web/` and short targeted checks
