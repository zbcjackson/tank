# Remove N2 and simplify SubAgent

> **Status:** In progress — 2026-10-02

## Scope

Remove both Yutori N2 plugins and all extension points whose only production
consumers are those plugins. Preserve the current Computer Use plugin and built-in
LLM agents, with one SubAgent extension path and host-owned task governance.
Historical plans and benchmark evidence remain as history; current documentation
and backlog must describe the retained implementation. Baseline: `3113fd83`.

## Steps

1. Remove plugins, agent definitions, configuration, credentials and dependencies.
2. Remove legacy engine/executor dispatch, unused pause/resume declarations,
   final_answer compatibility and N2-only model protocol declarations;
   simplify Runner, authorization and benchmark branches around retained callers.
3. Update tests and current documentation, mark historical N2 references retired,
   and remove obsolete backlog work. Commit each completed logical subtask.
4. Complete the verification checklist below, then the mandatory code-reviewer
   review-and-refactor gate (at most three rounds). Archive this plan on completion.

## Tests

- Before refactoring, run retained Computer Use/SubAgent governance regressions.
- Verify removed engine configuration cannot silently dispatch as a built-in agent.
- Verify bare final_answer cannot complete a SubAgent; use TaskResult in fixtures
  and retain cleanup/audit-failure evidence as unknown.
- Verify all task model calls require output limits after removing the N2 exemption.
- Keep Computer Use/ordinary LLM authorization, task input/result, model governance,
  cancellation, desktop lock and cleanup tests; remove only obsolete N2 branches.
- Run backend tests with Yutori and cua-driver absent from the synchronized workspace.
- Run existing chat E2E including Computer Use; remove the SDK-only scenario outline.

## Verification Checklist (final step)

1. `cd web && pnpm lint` — ESLint.
2. `cd web && npx tsc -b --noEmit` — TypeScript project references.
3. `cd backend && uv run ruff check core/src/ core/tests/ plugins/` — current workspace paths.
4. `cd backend && uv run pytest` — full backend workspace suite; use documented
   Opus library path and no-sync after installing all workspace packages if required.
5. `cd backend && uv run pyright <changed surviving Python files>` — fix type errors.
6. `cd cli && uv run ruff check src/ tests/` — CLI lint if affected (otherwise N/A).
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
   — inspect running backend reload; empty matching output passes.
8. `cd test && pnpm test` — existing E2E with backend/frontend running.
9. `python3 scripts/check_docs.py` — documentation consistency.
10. `python3 scripts/check_protocol_sync.py` — if protocol artifacts change (otherwise N/A).

## Results

Implementation complete; independent review pending.

- Removed both N2 plugins, engine/executor dispatch, provider model declarations,
  unused pause/resume capabilities, bare final_answer completion and SDK-only metrics.
- SubAgent now requires TaskResult and uses host-owned model/authority/cleanup;
  ordinary LLM agents and current Computer Use retain their existing task behavior.
- Local YUTORI environment entry removed without logging credentials. Workspace
  synchronization confirms Yutori, cua-driver and both plugin modules are absent;
  Computer Use browser/Vision extras remain installed.
- Lock validation passed with only 87 lines removed; no unrelated dependency changes.
- Test-first regressions: old engine config (2 failures before change, then pass),
  bare final_answer (1 failure before change, then pass). Retained caller baseline:
  9 passed. Final SubAgent/Computer Use targeted run: 248 passed.
- Full backend workspace: 5438 passed, 1 skipped, 21 dependency deprecation warnings
  (262.03 s). No paid model or native GUI interaction was required.
- E2E: 17 scenarios / 67 steps passed (74.02 s). SDK-only outline removed.
- Backend core/tests/plugins lint, changed-file pyright, web lint and tsc -b,
  docs consistency, git diff --check and dev reload error scan all passed.
- CLI lint and protocol sync are N/A: neither subtree/contracts/artifacts changed.
- Full suite command: `uv run --no-sync env
  DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/opus/1.6.1/lib pytest -q` from backend.
  Actual backend lint paths are core/src, core/tests and plugins; repository root
  src/tests paths in older instructions do not reflect the current workspace.

