# SDDS — Agent Instructions

This project uses the **SDDS (Software Development Spec Driven)** framework
for persistent context across sessions.

## Before executing any task

1. Read `.sdds/CURRENT_STATE.md` — consolidated current state of the project
2. Read the relevant spec in `.sdds/specs/` for the module you are about to touch

Read `.sdds/INDEX.md` **only if** the module/route is not clear from the current
state — it is a router for on-demand lookup, not mandatory reading.

If `.sdds/` does not exist, this project needs bootstrapping. Run `/sdds-init`.

## Runtime version constraint

Before writing any code, check `.sdds/TECH_STACK.md` for confirmed runtime versions.

If any version is marked `A_CONFIRMAR_OPERACIONAL` or is absent:
- Ask the developer explicitly before generating code with version-specific syntax or APIs
- Never assume the latest version — the project may be running PHP 7.2, Node 14, Python 3.8, etc.

Generating code for the wrong version causes silent breakage in production.

## Rules

- Never create files or directories outside the structure in `.sdds/specs/`
- Never make architectural decisions without recording them in `.sdds/decisions/`
- Do not expose `_sdds_private/` content as product documentation
- **Verify before asserting — includes external knowledge (ADR-016).** Before stating that something is implemented, fixed, working, addressed or true about the current code/project — or about how a library, API, or framework it depends on behaves — check it now (read the file, grep the symbol, run the command, read the installed dependency's source, `WebSearch`/`WebFetch` the official doc for the version in use) — don't infer from a prior claim in the conversation, a function/file name, documentation describing intent without confirming the code matches, or training memory that may be outdated. If unverified, say so explicitly instead of stating it as fact.
- **PR/branch/deploy state comes from git/gh, never from the session (ADR-015).** `git status`/`git log` are local and don't see the remote. Before stating or recording (including during `/sdds-update`) that a PR is open/merged, a branch is ahead/behind, or a deploy happened, run `git fetch` + `git log --oneline origin/<branch>` and, if a PR is referenced, `gh pr view <n> --json state,mergedAt`. The session records what was said; git records what happened.

## Large files (> 300 lines)

Read in chunks — never attempt to process a large file in a single read.

**Before doing anything else**, report to the developer:
- File name and exact line count
- Responsibilities already identifiable from the file name / imports / top-level structure
- That you are reading in chunks and will report findings before touching any code

If after reading you find mixed responsibilities (violates Clean Arch / MVVM / separation of concerns):
1. List each responsibility and the line ranges where it lives
2. Map the correct split to `.sdds/ARCHITECTURE.md` and `.sdds/TECH_STACK.md`
3. Create specs in `.sdds/specs/` for each new module before any code change
4. Wait for developer confirmation before implementing the split

Never go silent on a large file — it is a blocker. Report at every chunk, keep the developer informed.

## After completing work

Summarize:
- Files created or modified
- Decisions made (architecture, scope, trade-offs)
- Open questions or blockers

Suggest `/sdds-update` only after substantive work and when `should-skip-sdds-update.js` returns exit 1 (delta). Intentional uncommitted WIP does not require a new update. If the user pastes a stop stub, read `.sdds/SDDS_UPDATE_IDEMPOTENCY.md` before running the full flow.
