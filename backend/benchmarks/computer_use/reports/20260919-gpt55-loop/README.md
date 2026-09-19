# GPT-5.5 macOS calc-open closed loop — 2026-09-19

The production AgentRunner, computer_use definition, desktop tools, multiround
LLM transport and existing strict Calculator validator were exercised on a real
Mac. This was a three-trial **single-task diagnostic**, not the full 14-task suite.
Result: **2/3 strict passes**. All three final screenshots visibly showed 56;
trial 2 lacked the expression required by the current strict validator.

The user explicitly authorized cleaned live desktop screenshots for this run.
Other apps were temporarily hidden and both displays covered with plain local
windows. Calculator ran on the 1920×1080 primary display (3840×2160 backing).
The secondary display remained attached but was not tested. Calculator reopened
at a different position between trials; no display geometry changed. Hidden apps
and cover windows were restored after the test. Production config was not changed.

Real screenshots, full prompts and traces remain only in
`/tmp/tank-gpt55-loop/baseline/`. They are deliberately not committed. The
[summary](summary.json) retains scalar results, image hashes/dimensions, actions,
response hashes/model/provider, and the local input-isolation evidence.

## Actual model and closed-loop evidence

- OpenRouter `openai/gpt-5.5`, provider restricted to `openai`, fallbacks disabled,
  `require_parameters=true`, reasoning low, max_tokens=16000, temperature omitted.
- All 13 live API responses reported model `openai/gpt-5.5`, provider `OpenAI`.
  Total usage was 72140 tokens; seven screenshots were captured by production
  tools. Every transmitted image matched the current trial's screenshot archive.
- The last screenshot of each trial appeared in the next actual model request.
  The model's final response followed that image; the independent local validator
  then ran. HTTP bodies were checked before transmission; response streams were
  copied as consumed, not fully buffered before SDK parsing.
- Original instruction, tool schemas, 120-second timeout, 15-tool-call limit,
  reset and `trial-token-gui-calc-v4` scoring were retained. No model action was
  replaced with a precomputed coordinate or AX oracle click.

## Three trials

1. **Pass**, 28.93 seconds including setup/validation/teardown; three tool calls,
   four model rounds, two screenshots. Model batch-clicked normalized coordinates
   (545,435), (647,436), (579,435), (647,586): 7, ×, 8, =. Final screenshot showed
   7×8 and 56; AX validator passed.
2. **Strict failure**, 27.76 seconds; three tool calls, four model rounds, two
   screenshots. Model used `type_text("7*8")`, then Enter. Final screenshot showed
   56 but no expression; model declared completion and the strict validator
   rejected it. No mouse-coordinate action occurred in this trial.
3. **Pass after feedback**, 58.82 seconds; four tool calls, five model rounds,
   three screenshots. Pasting `7*8=` left 0. After receiving that screenshot,
   the model changed to four clicks at (681,361), (783,361), (714,361), (783,510).
   Final screenshot showed 7×8 and 56; AX validator passed.

Both four-click sequences succeeded at the application-result level. This does
not constitute eight separately instrumented target/event calibrations. No trial
timed out or attempted non-GUI tools. The old Part A driver reports cleanup as
`unknown`; that field is retained, not relabeled as SDK-style confirmed cleanup.

## New confirmed findings

**Production parameter incompatibility.** The initial synthetic preflight through
LLM.chat_stream failed with OpenRouter HTTP 404, “No endpoints found that can handle
the requested parameters.” The actual request included temperature=1.0. Replaying
the same generated image/request with only temperature omitted succeeded. The
production profile previously always emitted temperature and could not represent
omission. The fix accepts explicit YAML `temperature: null` and omits that key in
both streaming and non-streaming requests, preserving the previous default when
the key is absent and explicit numeric overrides including 0.0. Synthetic failed
and successful request/response records are archived here; paired request bodies
are identical except for temperature. This affected access to the model, not
coordinate scaling. The fix commit is `10104c5`.

**Calculator paste semantics and scoring.** Local-only replay through the same
TypeTextTool after independently verified zero reset reproduced:

- Paste `7*8` → AX result 56, no expression; Enter keeps that state.
- Paste `7*8=` → AX result 0.

Text containing punctuation uses clipboard paste in `_type_macos`, so typing an
expression is not equivalent to clicking the individual operator buttons. This
explains the observed trial 2 rejection and trial 3 retry without a coordinate
error. The natural-language task asks to compute and display 56; the stricter
validator additionally requires the visible expression. That mismatch needs a
separate scoring decision. We did not relax the validator or rewrite the failed
trial into a pass. Pixel checks here are local visual review, not a new OCR judge.

**Conflicting inherited instructions.** All live system messages contain both
the desktop-specialist definition and the instruction “ALWAYS delegate to the
computer_use agent immediately.” `AgentRunner._build_sub_agent_prompt` appends
`get_base_rules()`, whose packaged base.md includes that main-agent delegation
policy. The tool surface has no `agent` tool. The model explicitly noted the
conflict in its first response. This is direct request evidence of a prompt
conflict; its impact on accuracy is not isolated, and it was not changed here.

## Verification and limits

[Verification](verification.json): profile tests 30 passed, full backend 4484
passed/1 skipped, E2E 14 scenarios/55 steps, required lint/types/reload/docs/protocol
checks passed. The new HTTP tests cover null omission, unchanged defaults,
explicit numeric/zero overrides, and streaming/non-streaming paths.

This validates a real model-driven loop, including successful mouse batches and
one feedback-based recovery. It does not establish reliable completion of arbitrary
tasks, correctness across multiple displays, screenshot-free rapid clicking,
long-history compaction, Supervisor/voice integration, or the official N2 SDK.
Raw visual content stays local; reproducing this test needs the same explicit
live-screenshot authorization and a cleaned desktop.

Use the existing benchmark CLI from `backend/core`, with an isolated config
whose computer_use profile contains the parameters above and configured
OPENROUTER_API_KEY (never paste the secret into a command):

```sh
uv run python -m tank_backend.benchmarks --suite ../benchmarks/computer_use --agent computer_use --tasks '^calc-open$' --trials 3 --config /path/to/isolated/config.yaml --out /tmp/new-gpt55-loop
```

The local invocation added request/image assertions and a streaming response tee
to the existing driver; it changed no model messages, tool execution or scoring.
The CLI alone produces the standard report/traces, not these extra HTTP audit files.
