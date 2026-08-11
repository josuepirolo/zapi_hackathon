# SDDS — GitHub Copilot Instructions

This project uses the **SDDS (Software Development Spec Driven)** framework.

## Before suggesting any code

1. Check `.sdds/CURRENT_STATE.md` to understand the current project state
2. Read `.sdds/specs/[module].md` before suggesting changes to that module
   (use `.sdds/INDEX.md` to locate the spec only if the module is not obvious)

If `.sdds/` does not exist, the project has not been bootstrapped yet.

## Runtime version constraint

Before suggesting any code, check `.sdds/TECH_STACK.md` for confirmed runtime versions.

If a runtime version is marked `A_CONFIRMAR_OPERACIONAL` or is not present, do not suggest version-specific syntax or APIs. Ask the developer to confirm the version first.

Never assume the latest version — the project may be running PHP 7.2, Node 14, Python 3.8, MySQL 5.7, etc. Suggesting incompatible syntax causes silent breakage.

## Rules

- Follow conventions defined in specs strictly — do not invent patterns
- Never suggest creating files outside the structure defined in the specs
- When suggesting an architectural change, note that it requires an ADR in `.sdds/decisions/`
- **Verify before asserting — includes external knowledge (ADR-016).** Before stating that something is implemented, fixed, working, addressed or true about the current code — or about how a library/API/framework it depends on behaves — check it now (open the file, search the symbol, read the installed dependency's source, check the official doc for the version in use) — don't infer from a prior claim, a name, documentation describing intent without confirming the code matches, or training memory that may be outdated. If unverified, say so explicitly instead of stating it as fact.
- **PR/branch/deploy state comes from git/gh, never from the session (ADR-015).** Before stating that a PR is open/merged, a branch is ahead/behind, or a deploy happened, check `git fetch` + `git log --oneline origin/<branch>` and, if a PR is referenced, `gh pr view <n> --json state,mergedAt` — local `git status`/`git log` don't see the remote.

## Large files (> 300 lines)

Before suggesting any change, tell the developer: the file name, its exact line count, and the responsibilities you can identify from its name and structure.

Read in sections before touching anything. If the file mixes concerns (violates Clean Arch / MVVM / separation of responsibilities):
1. List each concern and the line range where it lives
2. Suggest the correct split following `.sdds/ARCHITECTURE.md` and `.sdds/TECH_STACK.md`
3. Note that each new module needs a spec in `.sdds/specs/` before code is written
4. Wait for the developer to confirm before proceeding

Never suggest a change to a large file without first surfacing the size issue explicitly.
