# CLAUDE.md

This project uses the **SDDS (Software Development Spec Driven)** framework.

## Session start (token-aware)

The `SessionStart` hook injects `.sdds/CURRENT_STATE.md` automatically as
"SDDS — Contexto automático de sessão". **If that injected context is present, do
NOT re-read `CURRENT_STATE.md` or `INDEX.md` — use what was injected.**

Fallback (no injected context): read `.sdds/CURRENT_STATE.md` only.

Read **on demand only** (never proactively):
- `.sdds/INDEX.md` — only if the module/route is not clear from the current state
- `.sdds/PROJECT.md` — only if project name/type/stack is needed and absent
- `.sdds/project-spec/README.md` — only before architectural decisions

If `.sdds/` does not exist: project needs bootstrapping. Run `/sdds-init`.
If `.sdds/project-spec/` does not exist: run `_sdds_private/08_SDDS_BROWNFIELD_PROJECT_SPEC.md` to create the living project spec.

## Mandatory at session end

- Run `/sdds-update` **only** after substantive work and when `node _sdds_private/scripts/should-skip-sdds-update.js` indicates delta (exit 1). If exit 0 (idempotent), cite `canonical_session` from `.sdds/.last-consolidation.json` — do not re-run the full flow.
- Before `/sdds-update` on a stop stub: read `.sdds/SDDS_UPDATE_IDEMPOTENCY.md`
- Update `.sdds/INDEX.md` if modules, specs or decisions were added or changed
- Update `.sdds/CURRENT_STATE.md` if there was operational impact
- Update `README.md` if any documented feature was added, changed or removed
- Update `.sdds/project-spec/` files impacted by changes in this session (new business rule → `09-regras-negocio.md`; new module → `00-visao-geral.md` + `03-estrutura-diretorios.md`; stack change → `01-stack-tecnologica.md`; architectural decision → `13-decisoes-arquiteturais.md`)

## Runtime version constraint

Before writing any code, check `.sdds/TECH_STACK.md` for confirmed runtime versions.

If a version is marked `A_CONFIRMAR_OPERACIONAL` or is missing:
- **Ask the user explicitly** before generating code that may use version-specific syntax or APIs
- Never assume a modern version — a PHP project may be running 7.2; a Node project may be on 14

Different versions mean different syntax, different APIs, and different available features. Generating code for the wrong version causes silent breakage.

## Rules

- Never create files outside the structure defined in `.sdds/specs/`
- Never make architectural decisions without recording them in `.sdds/decisions/`
- Never expose `_sdds_private/` content as product memory
- Always update `.sdds/project-spec/` when business rules, modules, stack, integrations or structure change
- **Verify before asserting — includes external knowledge (ADR-016).** Before stating that something is implemented, fixed, working, addressed or true about the current code/project — or about how a library, API, or framework it depends on behaves — check it now (read the file, grep the symbol, run the command, read the installed dependency's source, `WebSearch`/`WebFetch` the official doc for the version in use) — don't infer from a prior claim in the conversation, a function/file name, documentation describing intent without confirming the code matches, or training memory that may be outdated. If you haven't verified, say so explicitly instead of stating it as fact.
- **PR/branch/deploy state comes from git/gh, never from the session (ADR-015).** `git status`/`git log` are local and don't see the remote. Before stating or recording (including during `/sdds-update`) that a PR is open/merged, a branch is ahead/behind, or a deploy happened, run `git fetch` + `git log --oneline origin/<branch>` and, if a PR is referenced, `gh pr view <n> --json state,mergedAt`. The session records what was said; git records what happened.

## Large files (> 300 lines)

Never read a large file in one shot. Always use `offset` + `limit` to read in chunks.

**Before doing anything else**, tell the user:
- The file name and exact line count
- What responsibilities you can already identify from the file name / imports / structure
- That you will read it in chunks before proposing any change

If after reading you find the file mixes responsibilities (violates Clean Arch / MVVM / separation of concerns):
1. List each responsibility found and the line ranges where it lives
2. Propose the correct split following `.sdds/ARCHITECTURE.md` and `.sdds/TECH_STACK.md`
3. Create a spec in `.sdds/specs/` for each new module before writing any code
4. Wait for user confirmation before implementing the split

Never stall or go silent. A large file is a blocker — surface it immediately and keep the user informed at every chunk.

## Available commands

| Command | Purpose |
|---|---|
| `/sdds-init` | Bootstrap full `.sdds/` structure — detects stack, creates all files, configures hooks |
| `/sdds-update` | Update session memory: `sessions/`, `timeline/`, `CURRENT_STATE.md`, ADRs |
| `/sdds-status` | Show current state, risks, pending items and next recommended action |
| `/sdds-feedback` | Record standardized framework feedback in `feedback/<user_key>/<date>/` (local, no network) |
