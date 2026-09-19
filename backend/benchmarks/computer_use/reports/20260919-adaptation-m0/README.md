# Adaptation M0 / M1 offline baseline

2026-09-19. Execution started; effectiveness experiments remain pending.

- [Manifest](manifest.json): baseline revision, current local environment,
  configured endpoints, frozen adoption criteria, request caps and pending work.
- [Legacy SDK request](legacy-request.json): captured before changes at revision
  `8c2173b` through SubAgentDriver → AgentRunner → LLMAgent → OpenAI SDK.
- [Corrected SDK request](corrected-request.json): same configuration and task
  after the M1 prompt fix. Only `messages[0].content` differs. All 12 tool schemas
  and all model parameters are unchanged.

HTTP used an in-process fake transport returning a final text response. No real
model request, screenshot or desktop action occurred; this batch cost $0.
Credentials/headers are absent, home and username are redacted. Configured model
IDs are not evidence of current provider availability or actual response identity.
The manifest records the latter as unverified. Image detail `auto` describes the
existing screenshot path; these initial requests contain no image.

The original prompt told the desktop specialist to delegate to itself and to use
`ask_user`, although neither tool was advertised. The corrected prompt keeps
shared security/environment instructions and asks the agent to report missing
critical information when it cannot request clarification. Main-agent dispatch
rules remain in the main prompt.

Historical references retain their original scoring:

- [N2 33/42](../20260917-092518-n2-current-baseline/report.md), 465 API calls.
- [N2 SDK strict 4/36, smoke 2/6](../20260918-014936-n2-sdk-baseline/report.md),
  548 API calls, `trial-token-v2`.
- [Part A 7/42](../20260916-031026-partA-macos/report.md), 576 API calls.
- [GPT-5.5 Calculator 2/3 strict](../20260919-gpt55-loop/README.md): input
  semantics failure and self-delegation are distinct from coordinate errors.

This is a reproducible request baseline, not a new benchmark score. New holdout
layouts, historical failure replay corpus, prompt-only paired model A/B and
per-live-batch pricing remain pending. The active plan stays open.

Verification: backend 4490 passed / 1 skipped, including N2 and N2 SDK;
Cucumber 14 scenarios / 55 steps passed; web lint/TypeScript, backend and CLI
ruff, targeted pyright, backend reload log, documentation and protocol checks
passed. Backend tests used `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` to find
the installed Opus library. This is an execution environment setting, not a
production configuration change.
