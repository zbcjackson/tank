USER PREFERENCES:
- Preferred language: auto-detect from user's input
- Verbosity: concise — favor short answers, expand only when asked
- When modifying config files: explain what you're changing and why
- When running code: explain what it does before executing

<!--
Per-user preferences are stored at:
  ~/.tank/preferences/users/<slug>/preferences.md

Each line is a markdown bullet, optionally followed by `[source, YYYY-MM-DD]`.
Source tags:
  - pinned    durable; never expires, never evicted by entry cap
  - explicit  user said it directly via `manage_preference`
  - inferred  PreferenceLearner observed it from a turn

You can hand-edit `preferences.md`. Bullets without a `[source, date]` suffix
are treated as pinned. To deliberately pin a fact during a session, ask the
assistant to remember it (the `remember` tool is approval-gated).
-->
