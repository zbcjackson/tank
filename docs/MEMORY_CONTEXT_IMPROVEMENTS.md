# Memory & Context Improvements

A comparison of Tank against four reference agentic harnesses (Claude Code, OpenClaw, Hermes Agent, OpenCode) across five context/memory patterns, and a prioritized backlog of improvements and new features.

> **Created:** 2026-05-23
> **Last updated:** 2026-05-26 — Phase B shipped (IMP-7, IMP-6, IMP-1, IMP-8); IMP-4 dropped (see §0).
> **Scope:** `backend/core/src/tank_backend/` — `context/`, `memory/`, `preferences/`, `prompts/`, `agents/`, `llm/`
> **Reference repos:** `~/src/3rd/{claude-code, openclaw, hermes-agent, opencode}`

---

## TL;DR

Tank is already strong on three of the five patterns (Persistent Instruction Files, Scoped Context Assembly, Progressive Compaction) thanks to its 7-layer `PromptAssembler`, `ContextManager.prepare_turn`, and 5-phase `compact()` pipeline. Its **biggest gaps** are:

1. **Dream Consolidation** — Tank has no background/idle consolidation; references all do (OpenClaw's 6-factor weighted dreaming is the most mature).
2. **No `pinned` tier in `PreferenceStore`** — every learned entry decays at 90 days and the 20-entry cap evicts oldest first; "allergic to peanuts" should never decay or be evicted, but today there's no way to mark a fact durable, and no deliberate-write path for the assistant. *(Shipped in Phase A — IMP-2.)*
3. **Compaction observability and authority** — no `/compact` command, no focus-topic guided compression, no compaction lineage in the conversation store, no plugin hooks during compaction. *(`/compact` + focus shipped in Phase A — IMP-3; lineage still open in IMP-7.)*
4. **Sub-agent memory isolation** — Tank's `AgentGraph` is single-agent; no fork/isolated context like Claude Code's coordinator mode.

> **Dropped from scope:** Memory categories (originally IMP-4). Tank is a long-running service, not a project-scoped tool; there is no real "workspace" concept (cwd is not a project boundary), so the user/project/feedback/reference split adds bookkeeping without payoff. mem0 stays a flat per-user pool; preferences keep their existing `explicit`/`inferred`/`pinned` tiers.

Each improvement below is sized S/M/L, lists the file paths that need to change, and includes a test plan. Improvements are grouped by pattern with priority rankings (P0–P2) at the end.

---

## 0. Phase A — Implementation Notes (2026-05-26)

Phase A shipped IMP-2, IMP-3, and IMP-9. IMP-4 (memory categories) was on the Phase A list but has been **dropped from scope** — see the rationale in the TL;DR.

### IMP-2 (`pinned` tier + `remember` tool) — landed with deviations

- `remember` is **not** approval-gated. The spec called for `approval_policies.require_approval`, but commit `f0454a9` deliberately removed that. Rationale: `remember` only writes a small markdown bullet under `~/.tank/users/<slug>/preferences.md`; the data is local, hand-editable, and reversible via `unpin`. Round-tripping through an approval prompt added friction without a real safety benefit. The `consolidator` (IMP-1) inherits this same trust model when promoting `inferred → pinned`.
- `pinned_soft_cap_kb` is **not** implemented. The 12 KB soft warning was deferred until Dream (IMP-1) is available to consolidate oversized pinned sets — there's no point warning if there's no remediation path.
- `prompts/defaults/USER.md` was **not** updated with the tag-comment block describing `[explicit]` / `[inferred]` / `[pinned]`. Track as a small follow-up.

### IMP-3 (`/compact` + focus topic) — landed with deviations

- REST path is `POST /api/context/compact/{session_id}`, not `POST /api/conversations/{id}/compact`. Tank's API surface is session-keyed (matches `/api/context/usage/{session_id}` and the WebSocket handler), so this is consistent with the rest of the API.
- Voice intent goes through normal LLM tool dispatch (`compact_context` tool), not a direct system-intent handler. The LLM round-trip is ~200ms — acceptable for a manual user action, and avoids a parallel intent-classification path.
- `compact(focus=...)` bypasses anti-thrashing guards (`forced = focus is not None`) so explicit user intent always wins.

### IMP-9 (`/usage` + `/memory` introspection) — landed with deviations

- `/api/memory/{user_id}` returns a flat `{pinned, learned, facts}` shape with no `category` query parameter — IMP-4 was dropped, so there's no category dimension to filter on.
- Voice intents (`get_context_usage`, `get_user_memory`) are LLM tools, not direct routes. Same reasoning as IMP-3.

### IMP-4 (memory categories) — dropped, will not be implemented

Tank is a long-running service on a host. There is no project/workspace concept: cwd is the backend's own working directory, not a user-project boundary. Categorizing memories into `user / project / feedback / reference` would require either (a) inventing a synthetic workspace dimension that doesn't map to anything users actually use, or (b) leaving three of the four categories empty. mem0 stays a single flat per-user pool. `PreferenceStore`'s existing `explicit` / `inferred` / `pinned` tiers (IMP-2) cover the durability axis that categories were meant to provide.

### Knock-on effects on later improvements

- **IMP-6 (pre-compaction flush):** the structured output no longer carries a `category` field on facts. Decisions write straight to mem0 as plain text — no `category=reference` tag.
- **IMP-1 (Dream Consolidation):** the consolidator's promote/consolidate/archive logic operates on the flat pool. No category-scoped queries.
- **IMP-8 (hybrid recall):** unchanged — keyword + vector recall over a flat pool.

---

## 0b. Phase B — Implementation Notes (2026-05-26)

Phase B shipped IMP-7, IMP-6, IMP-1, and IMP-8 in that order (lineage first as a safety net for everything that follows). User decisions: separate `compactions` ORM table for lineage, new `consolidation` LLM profile with fallback to `default`, denormalised `conversation_messages` row table + FTS5 for hybrid recall.

### IMP-7 (Compaction lineage) — landed with one deviation

- The doc proposed "generalize the existing `NON_DESTRUCTIVE` mode". Implementation **kept** `NON_DESTRUCTIVE` as channel-only and added lineage purely to the destructive path. Rationale: NON_DESTRUCTIVE channels never mutate in place — there's no destructive event to record. Generalising would have meant rewriting every read path to derive context from history, a much larger refactor than IMP-7's intent. Lineage gives the same recoverability outcome without that surgery.
- REST routes added at `GET /api/conversations/{id}/compactions` and `POST /api/conversations/{id}/compactions/{cid}/restore`. The list endpoint omits `pre_compaction_messages` by default; pass `?include_messages=true` to fetch them.
- Restore semantics: re-inflate messages between system prompt and current tail, then delete the restored record and any descendants. Descendants are pruned via in-Python tree walk (SQLite has no recursive CTE shortcut here and the chain is short).

### IMP-6 (Pre-compaction flush) — landed as specified

- New module `memory/flush.py`. Hooks in `compact()` between tail-selection and Phase 3 summarization (line 745 in `manager.py`).
- Schema is `{facts_to_remember: [str], preferences_to_reinforce: [str], decisions: [{what, why}]}` — the `category` field from the original spec was dropped along with IMP-4.
- Writes are routed: facts and decisions → `MemoryService.store_turn`, preferences → `PreferenceStore.reinforce`. All fire-and-forget so the flush never delays compaction. Timeout-bounded (8s default); JSON parse failure / LLM exception / timeout all return empty `FlushResult` without raising.
- Reuses the `summarization` LLM profile when present, falls back to `default` — same precedence as the existing preference learner.

### IMP-1 (Dream Consolidation) — landed as specified, off by default

- Six-factor weighted scoring (frequency, relevance, diversity, recency, consolidation, conceptual). For diversity we use Jaccard similarity over word tokens with a character-bigram fallback for CJK / short text — no embedding lookup, cheap and bilingual.
- Three triggers: scheduled (daily 03:00 by default via `consolidation.schedule`), REST (`POST /api/memory/consolidate`), voice tool (`consolidate_memory`). All paths share the same `build_consolidator(app_config)` factory.
- Scheduler integration: added `CronScheduler.register_recurring(id, cron, callback)` for framework-internal recurring tasks that should not appear in `JobStore` or `manage_jobs`.
- New `consolidation` LLM profile slot in `config.yaml`. Falls back to `default` when unset.
- **Default is `consolidation.enabled: false`** — opt-in until tuned. Promote / consolidate / archive verdicts are auto-applied (no human approval) because they reuse the same trust model as the `remember` tool.

### IMP-8 (Hybrid memory recall) — landed as specified

- New `conversation_messages` row table mirrors each conversation's `messages` JSON one row per message. FTS5 virtual table on top uses SQLite's `trigram` tokenizer (built-in since 3.45) — handles English and CJK without a custom tokenizer.
- One-time backfill in the migration: parses every existing `conversations.messages` JSON blob into rows. Production DB picked up ~1114 messages on the first run.
- SQLite triggers (`AFTER INSERT/UPDATE/DELETE`) keep the FTS index in sync with the row table.
- New `HybridSearch` orchestrator runs vector (mem0) and keyword (FTS5) in parallel, dedupes by whitespace-normalised lower-cased text, fuses with reciprocal rank fusion (k=60). Cross-strategy hits earn the sum of both RRF scores so dual hits outrank single-strategy hits.
- `MemoryService.recall()` automatically routes through `HybridSearch` when both stores are wired — drop-in upgrade for callers that already pass through `recall()`. Falls back to vector-only when the messages store is absent.
- **Trigram caveat:** FTS5 trigram requires queries of ≥3 characters. Two-char Chinese keywords like "明天" alone won't match — most natural queries already satisfy this (e.g. "明天的", "会议室", filenames, identifiers).

---

## 1. Per-Pattern Comparison

### Pattern 1 — Persistent Instruction File

| Project | Status | Files / Convention | Layering | Imports |
|--------|--------|-------------------|---------|---------|
| **Tank** | ✅ Strong | `base.md`, `SOUL.md`, `USER.md`, `AGENTS.md` (user + workspace chain), `prompts/defaults/` | 7-layer with workspace-aware discovery via `AgentsFileResolver` | None — files merged in-place |
| Claude Code | Partial | `CLAUDE.md` (user + project + sub-dir), `@imports` | User > project > subdir > defaults | `@path` imports inside CLAUDE.md |
| OpenClaw | Strong | `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `MEMORY.md` | Workspace inode-cached, deterministic file order for cache stability | None |
| Hermes | Strong | `.hermes.md`/`HERMES.md` walk to git root; first match of `AGENTS.md`/`CLAUDE.md`/`.cursorrules` | First-match-wins between project conventions; SOUL always separate | None — but scans for prompt-injection patterns |
| OpenCode | Strong | `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md` (deprecated) | Global → project walk-up; contextual attach on file read | Remote http(s) URLs supported |

**Tank already does**: workspace AGENTS.md chain, scope tracking, per-section separators, file caching.

**Missing**: `@import` syntax inside instruction files, prompt-injection scanning at load time, remote URL instructions, contextual instruction discovery when reading project files (OpenCode's killer feature).

---

### Pattern 2 — Scoped Context Assembly

| Project | Status | Per-turn builder | Scopes |
|--------|--------|-----------------|--------|
| **Tank** | ✅ Strong | `ContextManager.prepare_turn` augments system prompt with `KNOWN FACTS` + `USER PREFERENCES` per user; non-destructive mode for channels | system, user, conversation, channel, attachments |
| Claude Code | Strong | `SessionMemory + AgentSummary + PromptSuggestion + AppState` reactive pipeline; <100ms latency target | session, project, user, agent, tool, permission |
| OpenClaw | Strong | Pluggable `ContextEngine.assemble()` interface; `AssembleResult` carries `messages`, `estimatedTokens`, `systemPromptAddition`, `contextProjection` | session, tool, model, citations |
| Hermes | Strong | 3-tier system prompt (**stable / context / volatile**) cache-friendly; per-turn `MemoryManager.prefetch_all` | session, project, user, tool, memory |
| OpenCode | Strong | `prompt.ts` runs `[skills, env, instructions, modelMsgs]` in parallel; plugin hook `experimental.chat.messages.transform` | model, agent, session, message |

**Tank already does**: per-turn augmentation, attachment materialization, channel-derived context, scope-change notes.

**Missing**:
- **Three-tier cacheable prompt** (Hermes pattern) — Tank currently rebuilds the entire system prompt when any sub-file changes; splitting into `stable / context / volatile` would maximize prompt-prefix cache hits.
- **Pluggable context-engine** (OpenClaw pattern) — Tank's assembly is hard-coded; no way to swap algorithms (e.g., for a channel-vs-direct or different LLM).
- **Plugin transform hooks** (OpenCode pattern) — no extension point for plugins to inject/transform context.
- **Context-projection epochs** — Tank rebuilds in-place; doesn't track stable epochs for caching backends (e.g., Anthropic's prompt caching).

---

### Pattern 3 — Tiered Memory

| Project | Status | Tiers | Categories | Retrieval |
|--------|--------|------|-----------|-----------|
| **Tank** | ✅ Decent | Working (`ConversationData`) + cross-session (mem0) + learned preferences (`PreferenceStore`) | Per-user only; no fact/feedback/project distinction | mem0 semantic search; preferences = token-overlap dedup |
| Claude Code | Strong | Ephemeral → session → persistent → shared → archived (5 tiers); `memoryAge.ts` lifecycle | user / project / feedback / reference / team | `findRelevantMemories` |
| OpenClaw | Strong | Short-term daily notes + long-term `MEMORY.md` + corpus supplements (wiki/external) | Recall store, phase signals, session corpus | Hybrid vector + keyword (`MemorySearchManager`) |
| Hermes | Strong | `MEMORY.md` (declarative) + `USER.md` (profile) + FTS5 session history + 1 external provider (Honcho/Mem0/etc.) | Semantic, keyword, temporal, peer | FTS5 + trigram (CJK) + provider-specific |
| OpenCode | Partial | Short-term (tail) + long-term (compacted head); no first-class long-term memory | n/a | Tail pointer + filterCompacted |

**Tank already does**: mem0 vector recall, per-user preferences with staleness (90d) + caps (20), reinforcement, USER.md per-user override.

**Missing**:
- **Memory categories** — no project / feedback / reference distinction. Helpful for "remember this is a Python project that uses uv" vs "user prefers Celsius".
- **Memory lifecycle stages** (Claude Code pattern) — active/warm/cold/archived/purged with retention by access frequency.
- **No `pinned` (durable) tier in `PreferenceStore`** — `source` field already supports `explicit`/`inferred`, but every entry is subject to the 90-day staleness sweep and the 20-entry cap. There's no way to mark a fact never-decay / never-evict, and no deliberate-write tool — the assistant can only nudge entries in through the per-turn learner. A `pinned` tier closes both gaps inside the existing module.
- **Session-corpus indexing** (OpenClaw pattern) — daily session transcripts indexed for keyword + semantic recall.
- **Hybrid keyword + semantic recall** — Tank only uses vector. Hermes shows FTS5 with trigram support is essential for CJK queries and exact symbol/ID matches.
- **Peer/speaker-card memory** — Tank has speaker ID; could attach per-speaker facts/preferences without recomputing every turn.

---

### Pattern 4 — Dream Consolidation

| Project | Status | Trigger | Output |
|--------|--------|---------|--------|
| **Tank** | ❌ Missing | Only on-demand incremental summarization inside `compact()` | `compaction_summary` system message |
| Claude Code | Partial | No explicit idle trigger; `/compact` + `AgentSummary` + `speculation.ts` | Speculative summaries, agent summaries |
| OpenClaw | ✅ Strong | **Scheduled cron**: light → REM → deep phases; 6-factor weighted promotion (frequency, relevance, diversity, recency, consolidation, conceptual) | `DREAMS.md` diary, `MEMORY.md` promotion, recall-store updates |
| Hermes | Strong | **Idle-triggered**: `min_idle_hours` + `interval_hours` gates; spawns forked AIAgent | Curator state, skill lifecycle transitions, archive moves |
| OpenCode | Partial | Async background summarization (step 1) | Anchored summary |

**Tank already does**: incremental summary that preserves prior summary on re-compaction.

**Missing — this is Tank's biggest gap**:
- **Idle/scheduled dreaming** — Tank has a `jobs/` subsystem (cron infrastructure) already, but no dreaming job.
- **Promotion from working/recent → long-term** with weighted scoring.
- **Dream diary** for human inspection (`~/.tank/DREAMS.md`).
- **Background skill/preference curator** (Hermes pattern) — auto-archive stale preferences, consolidate redundant ones.
- **Phase signals** (OpenClaw) — fast skim (light) → reasoning extraction (REM) → durable promotion (deep).
- **Run isolation** — auxiliary LLM that doesn't pollute the main session's prompt cache.

---

### Pattern 5 — Progressive Context Compaction

| Project | Status | Algorithm | User API |
|--------|--------|----------|----------|
| **Tank** | ✅ Strong | 5-phase: prune tool results → tail protection → incremental summarize → sanitize tool-pairs → fallback truncation; anti-thrashing (≥2 ineffective skips, max passes); dynamic budget from model `/models` endpoint | Auto-only; no command |
| Claude Code | Strong | Monitor → trigger (`/compact` or >80% full) → analyze → summarize → replace → verify | `/compact` |
| OpenClaw | Strong | **Pre-compaction memory flush** (silent turn) → compact → checkpoint; pluggable | `/compact` |
| Hermes | Strong | 5-phase very similar to Tank's; `/compress <focus>` for guided summary; session-lineage chain (`parent_session_id`) | `/compress <focus>`, `/usage`, `/insights` |
| OpenCode | Strong | Anchored summary + tail pointer in `CompactionPart`; replay on overflow; plugin hooks | Auto-only; `/compact` if exposed |

**Tank already does**: tool-result pruning + dedup, tail protection w/ 1.5x overshoot, incremental summary, tool-pair sanitization, anti-thrashing, dynamic budget detection, fail-safe truncation fallback.

**Missing**:
- **No user-facing compact command** — neither voice ("compact context") nor REST.
- **No focus topic** for guided summarization (Hermes' `/compress database schema`).
- **No pre-compaction memory flush** (OpenClaw) — a silent turn that saves "what's critical to remember" before the summary discards detail.
- **No compaction lineage** — Tank overwrites `conv.messages` in place; can't recover a pre-compaction view. Hermes uses `parent_session_id`; OpenCode uses `tail_start_id` + `CompactionPart`.
- **No plugin hook** during compaction.
- **No `/usage` view** — token budget, fill %, last-compaction stats are computed but not exposed via REST or tool.

---

## 2. Improvement Backlog

Each item has: **What**, **Why**, **Where** (file paths), **How** (concrete sketch), **Size** (S=1-2d, M=3-5d, L=>5d), **Tests**.

### P0 — Highest leverage, fills a structural gap

#### IMP-1: Dream consolidation pipeline (idle + scheduled) [L]

**What**: A background process that, when Tank is idle, distills recent conversations and preferences into durable memory and curates stale entries.

**Why**: Tank's preference learner runs per-turn (fire-and-forget), but there is no mechanism to (a) re-evaluate / consolidate / dedupe old preferences, (b) extract long-arc patterns from many sessions, or (c) prune cold memories. Without this, the preference store grows monotonically until it hits the 20-entry cap and starts dropping the oldest, regardless of importance.

**Where**:
- New module: `backend/core/src/tank_backend/memory/consolidator.py`
- Reuse: `backend/core/src/tank_backend/jobs/` (already has cron infrastructure)
- Hook into: `backend/core/src/tank_backend/preferences/store.py`, `backend/core/src/tank_backend/memory/service.py`
- New defaults: `backend/core/src/tank_backend/prompts/defaults/` — `DREAMS.md` template
- New config section: `consolidation:` in `backend/core/config.yaml`

**How** (sketch, in priority order):

```
Phase 1 — light: scan last 24h of preferences + recent mem0 entries
                 score by (frequency, recency, semantic_overlap)
                 emit candidates list

Phase 2 — REM:   for top-K candidates, call an LLM with a
                 distill-and-categorize prompt → producing
                 - "should_promote" facts (durable user truths)
                 - "should_consolidate" pairs (merge near-duplicates)
                 - "should_archive" entries (stale or contradicted)

Phase 3 — deep:  apply transitions:
                 - "should_promote": flip PreferenceStore.source from
                   inferred → pinned (escapes decay + cap)
                 - "should_consolidate": reinforce() the merged entry,
                   remove() the loser; rewrite mem0 vector if needed
                 - "should_archive": remove() from PreferenceStore;
                   delete the corresponding mem0 vector
                 append a dated entry to ~/.tank/DREAMS.md so the
                 user can inspect / undo
```

Triggers:
- Idle gate: only run if `(now - last_user_turn) > min_idle_seconds` (default 30 min).
- Interval gate: at most once per `interval_hours` (default 24 h).
- Manual: REST `POST /api/memory/consolidate` and a voice/skill tool `consolidate_memory`.

Run isolation: use a dedicated auxiliary LLM profile (`consolidation` in `config.yaml`) — never touches main pipeline's prompt cache.

**Size**: L (3 phases, new module, new config, new defaults, integration with jobs, tests)

**Tests**:
- Unit: scoring function with synthetic candidate sets (recency decay, overlap detection).
- Unit: phase-1 → phase-2 → phase-3 with mocked LLM (asserts correct promotion / archive actions).
- Integration: `consolidator.run()` against a real (test-scoped) `PreferenceStore` + mock `MemoryService`, asserts DREAMS.md grows and stale entries are archived.
- Idle/interval gate tests using fixed timestamps.

#### IMP-2: `pinned` tier in `PreferenceStore` + `remember` tool [S]

**What**: Add `pinned` as a third value to `PreferenceStore`'s existing `source` field (today: `explicit` / `inferred`). Pinned entries skip the 90-day staleness sweep and the 20-entry cap. Add a `remember` tool that lets the assistant deliberately pin a fact (approval-gated), and document `preferences.md` as user-editable.

**Why**: `preferences/store.py` already has 80% of what's needed: per-user markdown bullets at `{base}/users/{slug}/preferences.md`, source tagging (`store.py:96`), date suffixes, parser tolerance for old/sparse formats. The remaining gaps are (a) no way to mark a fact durable — every entry decays at 90 d (`_STALENESS_DAYS = 90`) and the 20-entry cap evicts oldest first, so "allergic to peanuts" is at the mercy of recency; (b) no deliberate-write path for the assistant — only `PreferenceLearner` can write, and it always writes `inferred`; (c) the file isn't documented as user-editable, so the `[source, date]` suffixes and auto-staleness sweep make hand-edits feel unsafe. Adding a `pinned` tier and an edit tool closes all three gaps inside one module — no parallel store, no new prompt section.

**Where**:
- `preferences/store.py`:
  - Extend the entry parser regex to accept `pinned` as a source.
  - In `_load_raw_entries`, skip the staleness check when `source == "pinned"`.
  - In `add_if_new`, skip the cap check when `source == "pinned"`.
  - In `render_for_user`, render pinned entries first (above inferred/explicit) so they sit at the top of `USER PREFERENCES`.
- `preferences/learner.py` — unchanged. Learner still writes `inferred`. Promotion to `pinned` is Dream's job (IMP-1).
- New tool: `tools/remember.py` (BaseTool) with `pin(text)`, `unpin(text)`, `list()`. Approval policy: `require_approval`. Reuses `PreferenceStore.add_if_new(..., source="pinned")` and `remove()`.
- `core/config.yaml` — add `remember` to `approval_policies.require_approval`.
- `prompts/defaults/USER.md` — add a comment block explaining how to hand-edit `preferences.md` and what each source tag means (existing `[explicit]`, `[inferred]`, new `[pinned]`).

**How**:
- Pinned entries persist in the existing format: `- Allergic to peanuts [pinned, 2026-05-23]`. The date is informational only — no decay applied.
- Hand-editing: a user can add a bullet without any `[source, date]` suffix. The existing parser's "old format" branch (`store.py:35`) already accepts this; treat unsuffixed entries as pinned.
- Soft cap: warn (don't truncate) in the rendered `USER PREFERENCES` section when pinned bytes exceed `pinned_soft_cap_kb` (default 12 KB). Dream (IMP-1) consolidates oversized pinned sets.
- No new prompt section, no new file, no new directory. Existing `[USER PREFERENCES]` section grows to render pinned bullets first.

**Size**: S — three small modifications to one module, one new tool, one config line.

**Tests**:
- Unit: `add_if_new(user, text, source="pinned")` is not subject to the cap; adding 25 pinned entries keeps all 25.
- Unit: pinned entries with date 100 days old survive `_load_raw_entries` (not auto-removed).
- Unit: `render_for_user` renders pinned entries first, then inferred/explicit.
- Unit: parser accepts a bullet with no `[source, date]` suffix and treats it as pinned.
- Tool: `remember.pin("Allergic to peanuts")` round-trips to `preferences.md` with `source=pinned`.
- Tool: `remember.list()` separates pinned from learned in its output.
- Approval: `remember.pin` is in `require_approval` and parks the call until the user confirms.
- E2E (Cucumber): "When the user says 'remember I'm allergic to peanuts' and approves, the next session injects that into `USER PREFERENCES` even after 91 days."

#### IMP-3: `/compact` command + voice intent + focus topic [M]

**What**: A user-triggered context compaction with optional focus, exposed via:
- voice: "compact context" / "compress conversation" intent
- REST: `POST /api/conversations/{id}/compact { focus?: string }`
- skill / tool: `compact_context(focus?)`.

**Why**: Auto-compaction happens at the budget threshold, but users (especially in long voice sessions) want to *proactively* free context before a complex task, or to *bias* the summary toward what matters next. All four reference projects have an explicit compact command; Hermes' focus-topic variant is the highest leverage addition.

**Where**:
- `context/manager.py:compact()` — extend signature with `focus: str | None = None`.
- `context/summarizer.py:summarize()` — already accepts `previous_summary`; add `focus` to the prompt template (`_SUMMARY_TEMPLATE`).
- New REST route: `api/conversations.py` or wherever conversation lifecycle lives.
- New tool: `tools/compact_context.py`.
- Voice path: handle intent in `BrainProcessor` or via a "system" skill (no LLM call needed — direct tool dispatch).

**How**: Pass `focus` to summarizer prompt:
```
RULES:
- ... (existing) ...
- Prioritize preserving information related to: {focus}
- Drop incidental details unrelated to the focus when over budget.
```

**Size**: M

**Tests**:
- Unit: `compact(focus="API design")` produces a summary that the LLM mock confirms includes the focus directive.
- Integration: REST endpoint compacts and returns before/after token counts.
- E2E (Cucumber): "When the user says 'compact the conversation about the database' then the recent turns are summarized into a focused summary".

#### IMP-4: Memory categories (facts / preferences / project / reference) — DROPPED

> **Status:** Will not be implemented. See §0 for rationale (Tank has no workspace concept). Original specification preserved below for historical context only — do not action.

**What**: Tag every stored memory with a category and surface them as separate sections in the system prompt. Categories match Claude Code's auto-memory schema (user / feedback / project / reference) plus Tank's existing per-user preferences.

**Why**: Currently `KNOWN FACTS ABOUT {user}` mixes everything mem0 returns. A user-fact ("Jackson prefers Celsius") and a project-fact ("this project uses uv, not pip") deserve different lifecycles and surfacing. Project facts shouldn't appear in unrelated workspaces; user facts should follow the user across projects.

**Where**:
- `memory/service.py` — add `category` to `store_turn` and `recall`. mem0 supports metadata filters.
- `context/manager.py:prepare_turn` — emit separate sections (`USER FACTS`, `PROJECT FACTS`, `REFERENCES`).
- `preferences/learner.py` — extend extraction prompt with category-classification.
- Add a `category` enum in `memory/types.py`.

**How**:
- Recall: filter mem0 by `metadata.category` and `metadata.scope` (user vs project).
- Project scope = workspace directory hash (already computed for AGENTS.md discovery).
- Storage: mem0 metadata: `{"category": "...", "user_id": "...", "workspace_hash": "..."}`.

**Size**: M

**Tests**:
- Unit: classification prompt extracts facts into correct categories (test fixtures for each).
- Unit: recall with workspace_hash filter excludes off-workspace project facts.
- Integration: a turn in workspace A doesn't leak project facts into workspace B.

### P1 — High value, lower structural risk

#### IMP-5: Three-tier cacheable system prompt (stable / context / volatile) [M]

**What**: Split `PromptAssembler.assemble()` output into three concatenated strings so the LLM client can place stable parts at the front for prompt-prefix caching, and only rebuild the volatile tier per turn.

**Why**: Currently the assembler rebuilds the whole prompt whenever `needs_rebuild()` is true (e.g., when workspace AGENTS.md is discovered for a new path). With Anthropic/OpenAI prompt caching, even a small change at the front busts the entire cache. Hermes' three-tier layout maximizes cache hits.

**Where**:
- `prompts/assembler.py` — return a `dataclass` with three fields instead of a single `str`.
- `context/manager.py:prepare_turn` — concatenate at message build time, with cache breakpoints between tiers (if provider supports it).
- `llm/llm.py` — pass cache breakpoints if using a caching-aware client.

**Mapping**:
- **Stable**: `[BASE]`, `[IDENTITY]`, `[GLOBAL RULES]`, `[SKILLS]` (skills only change when skill catalog changes).
- **Context**: `[WORKSPACE RULES]`, `[SCOPE]` (changes by workspace).
- **Volatile**: `[USER PREFERENCES]`, `[KNOWN FACTS]`, attachment placeholders, timestamp.

**Size**: M

**Tests**:
- Unit: stable tier is byte-identical across `prepare_turn` calls when no skill/global change.
- Unit: volatile tier changes per turn (timestamp).
- Integration: assert prompt cache hit ratio improves in a multi-turn run (mock provider returns cache stats).

#### IMP-6: Pre-compaction memory flush [S]

**What**: Before Phase 3 (summarize) of `compact()`, run a single silent LLM turn that asks "Are there facts in the about-to-be-summarized messages that should be persisted to memory before they're lost?" — and write the result to mem0 (vectors) and `PreferenceStore` (as `inferred` — never `pinned`, since pinning requires explicit user intent through the `remember` tool).

**Why**: Summarization compresses information; some details (a number, a name, a decision rationale) are easy to drop. OpenClaw's pre-compaction flush is its single most-cited safety feature. Tank's incremental summary helps but is best-effort — a flush is a backstop.

**Where**:
- `context/manager.py:compact()` between Phase 2 (tail selection) and Phase 3 (summarize).
- New helper: `memory/flush.py` — single-purpose LLM call with structured output.

**How**: Output schema:
```json
{
  "facts_to_remember": ["..."],
  "preferences_to_reinforce": ["..."],
  "decisions": [{"what": "...", "why": "..."}]
}
```
Routing: `facts_to_remember` → `MemoryService.store_turn` (vectors; Dream may later promote to a `pinned` preference if reinforced enough). `preferences_to_reinforce` → `PreferenceStore.reinforce()` to refresh timestamps. `decisions` → mem0 as plain text (one entry per decision, formatted `"<what> — because <why>"`). Flush failure is non-fatal — proceed with compaction.

**Size**: S (small new module, integrate into existing compact())

**Tests**:
- Unit: flush prompt produces a valid structured output for a synthetic conversation.
- Integration: compact() with flush enabled writes to PreferenceStore + MEMORY.md correctly.
- Failure: mocked flush exception → compact() continues without error.

#### IMP-7: Compaction lineage & non-destructive compaction by default [M]

**What**: Instead of replacing `conv.messages` in-place during compaction, persist the original messages (or a pointer to them) with a `compaction_id` and a `parent_compaction_id`. Conceptually: every compaction creates a new conversation revision; old revisions are read-only but recoverable.

**Why**: Today, if compaction summarizes badly, the original detail is gone forever. Hermes' session-lineage chain and OpenCode's `CompactionPart` + `tail_start_id` both retain enough metadata to recover. Tank already has a `NON_DESTRUCTIVE` compaction mode (only used for channels) — generalize it.

**Where**:
- `context/conversation.py` — add `compactions: list[CompactionRecord]` to `ConversationData`.
- `context/sqlite_store.py` — schema migration: `compactions` table.
- `persistence/migrations/` — Alembic revision.
- `context/manager.py:compact()` — write a record before mutating `conv.messages`.
- New REST endpoint: `GET /api/conversations/{id}/compactions`, `POST /api/conversations/{id}/compactions/{cid}/restore`.

**Size**: M

**Tests**:
- Unit: compact() with lineage emits a record with `tokens_before/after`, `compacted_count`, `summary_id`.
- Integration: restore endpoint round-trips messages back to pre-compaction state.
- Migration: Alembic up/down on a populated DB.

#### IMP-8: Hybrid memory recall (keyword + semantic) [M]

**What**: Augment mem0's vector search with keyword/FTS5 search over (a) recent transcripts, (b) MEMORY.md, (c) preferences. Combine via reciprocal rank fusion or simple weighted union.

**Why**: Vector search misses exact tokens (IDs, file paths, function names, CJK terms). Hermes specifically calls out this gap for Chinese — Tank is bilingual and currently relies on mem0's embeddings, which are weak for CJK exact-match queries. OpenClaw and Hermes both ship hybrid search; OpenClaw's `MemorySearchManager` interface is the cleanest design.

**Where**:
- New: `memory/search.py` — `HybridSearch` orchestrator with `vector_recall` + `keyword_recall` strategies.
- `memory/service.py:recall` — delegate to `HybridSearch.search`.
- `persistence/` — add FTS5 virtual table for conversation messages (mirror Hermes' trigram approach for CJK).

**Size**: M

**Tests**:
- Unit: keyword recall finds an exact filename in a conversation; vector recall misses it.
- Unit: hybrid fusion ranks the exact match above semantically-similar but lexically-different results.
- Bilingual: Chinese query (e.g. "明天的会议") retrieves Chinese turn that mem0 alone misses.

#### IMP-9: Voice/REST `/usage` and `/memory` introspection [S]

**What**: Expose what the assistant knows and how full its context is:
- `GET /api/context/usage` → `{tokens_used, budget, fill_pct, last_compaction_at, ineffective_count}`
- `GET /api/memory/{user_id}?category=...` → list facts/preferences/references for inspection
- Voice intents: "what do you remember about me?", "how full is your context?"

**Why**: Trust + debuggability. Currently a user has no visibility into either Tank's memory or its budget state. Hermes' `/usage` and `/insights` are praised as simple but very high-utility.

**Where**:
- `api/` — two new routes (read-only, no approval needed).
- `agents/chat_agent.py` or a new "system intent" handler — route voice queries to the routes (no LLM round-trip).

**Size**: S

**Tests**:
- Unit: usage endpoint returns correct numbers from `ContextManager`.
- Unit: memory endpoint paginates and respects category filter.
- E2E: voice "what do you remember about me?" returns a spoken summary.

### P2 — Nice to have / future investment

#### IMP-10: @-imports inside instruction files [S]

**What**: Support `@path/to/file.md` inside `AGENTS.md` / `SOUL.md` / `USER.md` etc. Resolved at assembly time, recursively (with cycle detection).

**Why**: Claude Code uses this to share common rules between projects (e.g., "all my projects follow `@~/.claude/python.md`"). Tank's user has multiple repos; without imports every project gets a copy-paste AGENTS.md.

**Where**:
- `prompts/resolver.py` — already loads files; add `_expand_imports(text, base_dir)` with cycle detection and max-depth.
- Tests for cycles, missing files (warning, not error), depth cap.

**Size**: S

#### IMP-11: Prompt-injection scanner on instruction load [S]

**What**: Scan `SOUL.md`, `USER.md`, `AGENTS.md`, MEMORY.md (and remote content if IMP-15 lands) for prompt-injection patterns at load time. Block + log on match.

**Why**: Hermes does this; the regex list (invisible-unicode, "ignore previous instructions", system-prompt-override, exfil curl) is small and the false-positive rate is low on instruction files that humans actually write.

**Where**:
- `prompts/sanitizer.py` (file already exists; extend with `scan_for_injection(text) -> list[Threat]`).
- `prompts/resolver.py` — call scanner; on match, log warning and replace file content with a `[BLOCKED]` placeholder.

**Size**: S

#### IMP-12: Pluggable ContextEngine [L]

**What**: Define an `interface ContextEngine { async assemble(conv, ...) -> AssembleResult }` and refactor `ContextManager.prepare_turn` into a default `LegacyContextEngine` that delegates to today's logic. Allow plugins (via the existing `plugin/` system) to register alternative engines.

**Why**: Tank has channels-vs-direct as a hard-coded `CompactionMode` branch. As more modes appear (voice-only, headless, batch), the branch grows. OpenClaw's pluggable engine isolates this.

**Where**:
- New: `context/engine.py` (interface + LegacyContextEngine).
- `plugin/` — register slot.
- Tests for slot resolution + fallback to legacy.

**Size**: L

#### IMP-13: Plugin hooks during compaction [S]

**What**: `experimental.session.compacting(messages, context, prompt)` and `experimental.chat.messages.transform(messages)` hooks (mirroring OpenCode), allowing plugins to inject reminders or transform messages.

**Why**: Today's only extension point is the assembler. Hooks during compaction let a plugin (e.g., a privacy plugin) scrub PII before summarization, or a domain-specific plugin (e.g., a code-review skill) inject a checklist.

**Where**:
- `context/manager.py:compact()` and `prepare_turn()` — emit Bus events at hook points.
- `plugin/` — declare hook names.

**Size**: S

#### IMP-14: Speaker-scoped memory pinned by speaker ID [M]

**What**: Tank already runs speaker identification. Pin a small "speaker card" (last few facts confirmed for this voice) to the system prompt the moment speaker ID resolves, ahead of the broader mem0 recall.

**Why**: Reduces mem0 latency on every turn (speaker card hits instantly), and surfaces "this is Jackson, who prefers Celsius" before the LLM sees the user message. Hermes' Honcho peer-cards prove the pattern.

**Where**:
- `pipeline/processors/asr_speaker_merger.py` — emit Bus event `speaker_resolved`.
- New `memory/speaker_cards.py` — small SQLite table mapping speaker_id → top-N facts.
- `context/manager.py:prepare_turn` — read speaker card first, then mem0 (mem0 still queried for query-specific recall).

**Size**: M

#### IMP-15: Remote instruction URLs [S]

**What**: Allow `@https://...` imports (with cache + signature check) in instruction files.

**Why**: OpenCode supports this. Useful for org-wide policy ("`@https://internal.example/agent-rules.md`"). Lower priority for a personal voice assistant.

**Size**: S

#### IMP-16: Sub-agent context isolation (coordinator mode) [L]

**What**: Allow a tool/skill to spawn a sub-agent (`AgentGraph` instance) with its own isolated `AgentState` and message history, with explicit pass-back of results to the parent.

**Why**: Claude Code's coordinator mode is the canonical example; useful for long-running research tasks (web search → summarize) without polluting the main conversation. Lower priority for voice (voice latency favors single-agent), but a clear win for long chat sessions.

**Size**: L

---

## 3. Priority Roadmap

A suggested 3-phase execution order. Each phase is independently shippable; subsequent phases assume earlier ones.

### Phase A — Foundations (P0) | ~2-3 weeks — ✅ SHIPPED (2026-05-26)
- ✅ **IMP-2** `pinned` tier + `remember` tool (autonomous, not approval-gated — see §0)
- ❌ **IMP-4** Memory categories — **dropped** (see §0; no workspace concept in Tank)
- ✅ **IMP-9** `/usage` + `/memory` introspection — REST + voice tools
- ✅ **IMP-3** `/compact` command + focus topic — REST + voice tool

### Phase B — Consolidation & resilience (P0/P1) | ~3-4 weeks — ✅ SHIPPED (2026-05-26)
- ✅ **IMP-7** Compaction lineage & restore — `compactions` table, REST list/restore (kept channel `NON_DESTRUCTIVE` as-is — see §0b)
- ✅ **IMP-6** Pre-compaction memory flush — silent LLM extraction before summarize
- ✅ **IMP-1** Dream consolidation pipeline — 3-phase, 6-factor scoring, daily cron, REST + tool, off by default
- ✅ **IMP-8** Hybrid memory recall — denormalised `conversation_messages` + FTS5 trigram, RRF fusion in `HybridSearch`

### Phase C — Polish, performance, extensibility (P1/P2) | ~3-4 weeks
- **IMP-5** Three-tier cacheable prompt — cost/latency win
- **IMP-14** Speaker-card memory — leverages existing speaker ID
- **IMP-10** `@imports`, **IMP-11** injection scanner, **IMP-15** remote URLs — small, ship together
- **IMP-13** Plugin compaction hooks
- **IMP-12** Pluggable ContextEngine (only if a second engine is on the horizon)
- **IMP-16** Sub-agent coordinator (defer unless a concrete use case arrives)

---

## 4. Cross-cutting Notes

### Configuration footprint
Most improvements add config under `backend/core/config.yaml`. Proposed shape (additive):

```yaml
memory:
  provider: mem0           # existing
  # IMP-4 (categories) was dropped — mem0 stays a flat per-user pool.
  hybrid_search:
    enabled: true          # IMP-8
    keyword_weight: 0.4
preferences:
  staleness_days: 90       # existing — does not apply to pinned
  max_entries: 20          # existing — does not apply to pinned
  # IMP-2 pinned_soft_cap_kb deferred until IMP-1 can consolidate oversized pinned sets.
consolidation:             # IMP-1
  enabled: true
  min_idle_minutes: 30
  interval_hours: 24
  llm_profile: consolidation   # auxiliary LLM, not main
  promotion:
    weights:
      frequency: 0.24
      relevance: 0.30
      diversity: 0.15
      recency: 0.15
      consolidation: 0.10
      conceptual: 0.06
context:
  cache_tiers: true        # IMP-5
  compaction:
    focus_supported: true  # IMP-3 (shipped)
    pre_flush: true        # IMP-6
    keep_lineage: true     # IMP-7
prompts:
  imports_enabled: true    # IMP-10
  injection_scanner: true  # IMP-11
  allow_remote: false      # IMP-15 (opt-in)
```

### What we are NOT doing (and why)

- **A parallel `MEMORY.md` store next to `PreferenceStore`**: the reference projects ship `MEMORY.md` because they don't have a per-user preferences store; Tank does, and `preferences.md` already holds short factual bullets per user. The only gaps are a never-decay tier and a deliberate-write tool — both fit inside the existing module (see IMP-2). A second store would duplicate data shape, parsing, persistence, and rendering paths for no new capability.
- **Per-message embeddings stored in SQLite**: vector storage belongs in mem0 / Chroma; duplicating it in SQLite couples persistence layers.
- **Multiple external memory providers concurrently**: Hermes explicitly forbids this; Tank should too. Tool-schema bloat and conflicting recalls hurt more than they help.
- **A separate "context store"** beside conversations: today's `ConversationStore` + `ContextManager` is the right boundary. Adding a third store complicates persistence migrations.
- **Real-time consolidation**: latency would compete with the voice pipeline. Idle/scheduled only.

### Testing strategy

Every improvement above should add (a) unit tests with mocked LLM / store and fixed timestamps, (b) integration tests across the changed seams (e.g., `compact() → MEMORY.md → next prepare_turn()`), and (c) where user-facing, an E2E Cucumber scenario under `test/`.

Existing checklist (CLAUDE.md §"Verification Checklist") still applies — ESLint, tsc, ruff, pytest, pyright, dev-server tail, E2E.

---

## 5. Inspirations Credit

| Idea | Borrowed from |
|------|---------------|
| Pinned/durable tier in preferences + edit tool | OpenClaw, Hermes (`MEMORY.md`) |
| Dream consolidation with phases & weights | OpenClaw |
| Idle-triggered curator | Hermes |
| Focus-topic guided compaction | Hermes (`/compress <focus>`) |
| Pre-compaction memory flush | OpenClaw |
| Three-tier cacheable system prompt | Hermes |
| Compaction lineage / non-destructive default | OpenCode (`CompactionPart`) / Hermes (`parent_session_id`) |
| Memory categories (user/project/feedback/reference) | Claude Code |
| Hybrid keyword + semantic recall (with FTS5 trigram) | Hermes, OpenClaw |
| Pluggable ContextEngine | OpenClaw |
| `@imports` in instruction files | Claude Code |
| Prompt-injection scanner on load | Hermes |
| Plugin hooks during compaction | OpenCode |
| Sub-agent coordinator mode | Claude Code |
| Speaker-card / peer-card | Hermes (Honcho) |

All ideas are reimplementable in Tank's existing architecture — no rewrite required.
