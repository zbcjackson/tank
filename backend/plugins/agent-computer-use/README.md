# Computer Use host loop — S0–S3 adapters

This opt-in `type: subagent` plugin uses the existing Runner/Adapter lifecycle.
It does not change the production computer-use agent or grounding modes.
The default factory currently has **no live channel or model transport**: a valid
goal returns `stopped / observation_unavailable`, with zero desktop/model calls.
Unknown private configuration keys are rejected. S1 provides injectable AX/OCR
observations; S2 adds explicitly configured managed Chromium. Native desktop
execution and Advisor domain wiring remain later stages. S3 adds an opt-in Jev Choice route.

The constructor accepts separate observation, action, selector and Advisor
implementations. Tests inject semantic fake UI boundaries through the actual
registry, AgentTool, approval, Supervisor, Runner and SQLite path. The core Adapter
owns task shutdown: it closes the runtime and joins in-flight operations before
calling the inherited `SubAgent.aclose()`. The base class owns the resource
collection and closed state; Computer Use only registers its channels with
`own_resource`. Cleanup uses the same path whether or not `run()` started and
never closes the borrowed runtime. A closed plugin cannot run again. `TaskResources` attempts other
releases after one fails and shares the outcome across repeated close calls.
Unconfirmed cleanup quarantines the desktop. Cancellation retains journaled effects.

## Current contract

`task_input` is a version-1 goal with `objective`, one bound `scope`, `inputs`
(key/value strings), ordered semantic `milestones`, and `completion` predicates.
Each milestone declares an ID, click/fill operation, role, label, fill input key
when applicable, and a key/value postcondition. These are semantic objectives,
not coordinates or native handles. Duplicate IDs and unknown fields are rejected.
The host assigns goal/action/candidate IDs and binds decisions to the goal
version, observation, scope, generation and candidate set.

The initial evaluator compares facts supplied by the trusted observation adapter.
Missing evidence never establishes completion. Actual file provenance, overwrite
protection and application-specific evidence are **not**
implemented by these offline fixtures and must be established by future adapters.
The PDF fixture's `new_pdf=verified` is synthetic evidence, not a filesystem check.

Exact unique actionable controls use rules. Non-exact role-compatible candidates
may use an injected selector; duplicate exact labels, incomplete scopes, missing
inputs, disabled controls and OCR text regions cannot bypass candidate admission.
Advisor can supply only previously unbound declared inputs, select one existing
candidate, request another observation, or return unable/needs-user-input. It
cannot change scope, completion criteria, existing inputs or permissions. This
batch does not support natural-language goal synthesis or milestone patches.

Core `TaskRuntime` registers the observation and dispatch adapters, retains bounded
call records bound to the worker task ID, and rechecks authority after asynchronous
preflight and before dispatch. Native parameter/reference validation remains in
the adapter. There is no generic resume or live policy/OS isolation claim.

Limits are task-local: 32 admitted action attempts (including rejected preflights,
also bounded by host `max_steps`), 64 observations, four Advisor calls, two
readbacks per unresolved effect. The
same semantic state is not resubmitted to the selector after abstention. Every
awaited boundary is followed by an authorization/cancellation/deadline/budget
check before dispatch. Native adapters must also check at their actual dispatch
boundary. Sent/unknown effects are journaled before awaiting a reply, verified
with reads, and never automatically retried. Partial/unknown/needs_input/stopped
remain distinct. Reusing a controller is rejected; generic resume is not implemented.

Selector/Advisor remain injection seams. The cross-caller acceptance suite runs
an Advisor fixture through the host TaskModel and real SDK with fake HTTP, sharing
authority, accounting and audit. This establishes the S0 core connection, not a
live Advisor/Jev implementation. Unwired benchmark transports remain rejected.

## Tests

From `backend/`, after installing the workspace plugin:

```bash
uv run --no-sync pytest plugins/agent-computer-use/tests -q
```

The existing `test/features/chat.feature` includes two isolated contracts for
this package. They complement the browser/WS suite; they do not claim live desktop
or real-model acceptance.

## S1 observation adapters

`AXObservationSource` reads the window/display bound by a host-supplied M2 frame.
It retains task-local native identities across list reordering, carries ancestors,
focus and value, and drops references when elements disappear. Native objects never
enter `Snapshot` or `snapshot_text()`. AX node/depth/children and text truncation make
the scope incomplete; ambiguous window geometry is rejected. Fill candidates need
an observed settable AXValue; click candidates need AXPress. Candidate construction
checks the full scope before keeping up to 32 options, with total/truncation metadata.

`VisionObservationSource` receives a host capture callback and uses a separate
local OCR snapshot. `recognize_text` requires the bound PNG hash/dimensions, runs
Vision revision 3 (accurate, zh-Hans/en-US, no language correction), and retains
image-pixel text boxes. Global points use the existing M2 `Observation.map_point`.
These are text regions with **no executable actions**. AX and OCR are not merged.
The optional `vision` extra installs PyObjC Vision 12.2 on macOS; imports are lazy,
and missing bindings return an unavailable observation. PNG/region/text limits are
bounded. Both adapters run within the controller's registered read operation and
check task authority at their native boundary; they do not create a live executor.

The [S1 acceptance](../../benchmarks/computer_use/reports/20260930-s1-observation/README.md)
contains frozen synthetic fixtures, native Vision outputs and limitations. The
factory remains unavailable until live channel/execution wiring is explicitly added.

## S2 managed Chromium

Install from `backend/`:

```bash
uv sync --all-packages --all-groups --extra browser
uv run --no-sync playwright install chromium
TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest plugins/agent-computer-use/tests/test_dom.py -q
```

Configure the existing extension explicitly (no model profile is needed):

```yaml
subagents:
  agent-computer-use:agent:
    config:
      browser:
        scope: managed-page
        url: http://127.0.0.1:8080/form
        # frame_name: editor  # optional unique leaf frame
```

The extension declares desktop and network permissions; the same task approval
covers them. The factory only validates configuration and creates inert adapters.
The first admitted observation starts one headless Chromium with a fresh,
non-persistent context. It never attaches to a user profile or existing browser.
HTTP(S) resources/navigation are confined to the configured origin and bound
page; other pages are never selected by URL/title. Service workers, WebSockets
and downloads are disabled. This is a trusted adapter, not a hostile-page sandbox.

One task-bound page and one frame supply bounded semantic observations. A named
frame must match exactly once and have no child frames. Without `frame_name`,
only a frame-free main page is accepted. Replacement/detachment requires a new
task; navigation invalidates old references. A task-local selector engine retains
actual element identities, so locators do not silently select replacement nodes.
The same locator engine serves observation, dispatch and readback; native handles
never leave the channel.

Supported action templates are button/link click and editable textbox fill.
Names use aria-labelledby, aria-label, native labels or element text. This is a
bounded subset of DOM semantics, not a full accessible-name implementation.
Visible unique `role:label` observations produce facts with the current input
value or text content, e.g. `textbox:Name = 小明` and `status:Result = 小明`.
Goals must use these page predicates; a page message alone does not prove external
persistence or file creation. Duplicate keys supply no fact. DOM/node/text caps
and open shadow roots make the scope incomplete; shadow DOM is not supported.

Click and fill require a successful non-forced trial click plus fresh identity,
state and task checks. Native input has a short timeout; while a command is
pending, task authority is monitored and stopping closes the owned browser.
There is still a browser/host race after any check: uncertain effects remain
unknown and are never replayed. Readback may confirm an effect even if its reply
was lost. Runtime quotas remain shared across observations and actions.

Ordinary pytest explicitly skips browser tests when the optional dependency or
Chromium executable is absent. `TANK_REQUIRE_CHROMIUM=1` makes either absence a
failure; the dedicated manual Backend CI job uses it. The existing chat.feature
also has a real Chromium contract scenario and requires this extra/browser for
`cd test && pnpm test`. It exercises Runner/config/results and stop boundaries
in an isolated process, not browser-agent transport through the chat WebSocket.
No paid model call or personal browser input is part of S2 acceptance.

## S3: explicitly configured Jev Choice

Jev is a core-managed decision model. Core uses the official `typesafe-sdk==0.7.2`
async client; the plugin only constructs the UI choice question and consumes
`context.runtime.decision_model.choose(state=..., instructions=..., options=...)`.
The returned `ChoiceResult` contains choice, confidence, probabilities and optional input/output token counts, not an
SDK response or executable tool call. No provider URL, credential, SDK or model
version is configured inside `JevSelector`.

Runner resolves an extension agent's `decision-model: <name>` against core
`decision_models` profiles (url/model/credential_env) before creating the
SubAgent. Only Jev with a fixed `jev-X.Y.Z` version is supported by this
capability. Core resolves the selected environment key (`core/.env` is loaded by
normal server startup), owns the lazy SDK/client and closes it with the task.
Unknown profiles, invalid model configuration and missing credentials fail
before the agent factory. Existing text `model: <name>` profiles remain separate
capabilities under the same core configuration and task lifecycle.

Core `DecisionModel` calls the official SDK directly and works without a task.
`TaskDecisionModel` borrows it, adding task checks, cancellation/deadline and the
original usage ledger. SDK retries are disabled. The SDK owns its default HTTP client (including environment
proxy/certificate behavior); no JevChoiceRoute, bridge,
TaskModelTransport or custom SSE parser remains. Known usage survives invalid
choices; unavailable usage is recorded as unknown. This is SDK-invocation accounting,
not proof of the exact network-send phase. Experimental policy/capture hooks are
explicit and receive model-call parameters/results, not HTTP objects.

Langfuse and existing task events provide optional observability; failures do not
block production model calls. UI/desktop operations retain their separate required
audit and dispatch checks. `json_models` / `json-model` remain retired: use
`decision_models` / `decision-model` and remove `extension`/`provider` from the
profile. The single decision implementation does not need a provider discriminator.
Runtime API is now 3; older declared versions are rejected before plugin creation.

The selector sends only the current structured snapshot, goal and bound whole
ActionSet, with explicit none/ambiguous/need_more_context/escalate choices. It
rejects incomplete or stale evidence, mismatched model versions, unknown choices,
invalid distributions and invalid confidence. Distribution sum tolerance is 0.02
for wire rounding; it is not an acceptance-confidence threshold or calibration
claim. Rules still bypass the model. Model results cannot change action arguments,
permissions or completion evidence. Only Choice is implemented. S3
bounded strategy evaluation is complete without a net-benefit adoption result;
Score/Noul and S4 goal planning are not part of this SDK migration. The historical
three-case smoke used the previous raw HTTP implementation. See the
[smoke record](../../benchmarks/computer_use/reports/20261003-s3-jev-smoke/README.md).

Run the fake HTTP and Controller/Adapter acceptance from `backend/`:
`uv run --no-sync pytest plugins/agent-computer-use/tests/test_jev.py -q`.


Merge [config.example.yaml](config.example.yaml) into the host configuration. The
Jev profile is defined in [core/config.yaml](../../core/config.yaml); configure
TYPESAFE_API_KEY in the host environment. For a different host config see the
[core setup guide](../../DEVELOPMENT.md#core-decision-models). Explicitly select an agent definition such as:

```yaml
---
name: computer-use-ladder
extension: agent-computer-use:agent
decision-model: jev
---
Complete the structured task goal within its approved scope.
```

Enable the `agent-computer-use:agent` SubAgent through the existing plugin manager.
No provider extension is registered. The private config `selector: jev` borrows
the configured core decision capability. Without this selector, the existing rule-only behavior remains. Merely
having `TYPESAFE_API_KEY` in the environment does not enable Jev or change the
production agent. A structured `task_input` goal is still required.

The real Chromium + fake HTTP config regression is in `test_dom.py`:
`TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest plugins/agent-computer-use/tests/test_dom.py -q`.
The paid smoke harness is an explicit opt-in: from backend run
`uv run --no-sync python benchmarks/computer_use/jev_smoke.py --live --output <new-directory>`.
It uses at most three requests, one per case, with no automatic retry; it stops on
failure/unknown usage and writes synthetic-only wire evidence and its spend journal.

### Selector evidence contract (version 1)

The Jev request now carries `state.evidence_contract`. Goal inputs are task or
Advisor declarations; milestone/completion predicates describe desired outcomes.
Snapshot facts/elements are reports from the current observation channel, bound
by the existing observation ID/scope/generation. They are not independent proof
of backend business state. The contract does not add a business-evidence provider,
verify claims, or upgrade a page value into an authoritative business fact.

The selector proposes one offered complete action or an existing control result.
It is instructed to retain refusal for missing/conflicting required evidence or
ambiguous targets, while avoiding invented unrelated prerequisites. Observation
text is data, not permission to override these instructions. This is model guidance,
not a prompt-injection security boundary or a guarantee that the model obeys it.
Host authorization, binding checks and effect verification still govern execution.
No synthetic `business_state` or blanket business-approval assertion is injected.

These instructions have offline contract coverage; the v3 paid results concern
its frozen diagnostic prompts and do not validate this different production prompt
or its four control categories. The default factory remains opt-in. Historical
v1/v2/v3 archives remain unchanged; changing the pinned Jev source intentionally
makes their current-worktree replay validation fail. Reproduce at the recorded
execution commit or freeze a new experiment, never overwrite historical hashes.

### Next held-out validation protocol

Before another paid run, freeze a fresh scenario-family split and new request digest.
Use new domains outside the twelve diagnostic cases, with paired sufficient-evidence,
missing-identity, conflicting-evidence and page-instruction-injection variants.
Author expected outcomes separately from model-visible inputs, review the provenance
of every fact, and freeze labels before viewing model responses. Any authored facts
remain synthetic; real integration acceptance separately requires channel/API evidence.

Compare the previous selector prompt with this exact version-1 contract using the
same model, candidates and host gates. Preserve the four production control options;
score intended-action coverage, wrong targets, negative actions and refusal types
separately. Include invalid/failed/not-run cases in denominators. Counterbalance order,
trace connection reuse, reserve usage and declare repetitions before execution.
Do not tune on this holdout; failures become development cases and require a new
holdout for later claims. This protocol is not a prepared dataset, frozen paid batch
or production acceptance. No additional live requests are part of this change.

The [first new synthetic holdout preparation](../../benchmarks/computer_use/fixtures/s3-holdout/README.md)
now contains 24 label-separated scenarios and 48 paired planned Jev requests. It
uses the actual production payload builder; its six domains share one two-row layout.
The separately frozen `s3_holdout_live` adapter connects these requests to host
transport, budgets and audit. The [approved execution](../../benchmarks/computer_use/reports/20261003-s3-holdout-live-prepared/README.md)
returned 48 valid responses; both arms scored 24/24, with no measured correctness
advantage for the contract. New executable batches require their own approval before
paid execution. This is not production acceptance.

### Real DOM multilayout acceptance

[The local acceptance record](../../benchmarks/computer_use/reports/20261003-s3-dom-multilayout/README.md)
exercises real isolated Chromium across toolbar, table and HTML-dialog layouts. It
checks DOM-origin snapshot serialization, complete-action selection, bound dispatch,
fresh effect readback, stale-reference rejection and no replay of an unverified effect.
Model HTTP uses fixed fixture responses, so these are integration/control-boundary
results, not new evidence of Jev accuracy or production adoption. Missing/conflicting
identity cases check handling of scripted refusals, not automatic host business validation.
Page values and page click logs do not establish external persistence. Native AX input,
real accounts, arbitrary websites and actual-model multilayout acceptance remain separate.

The [real Jev DOM batch result](../../benchmarks/computer_use/reports/20261003-s3-dom-live-prepared/README.md)
reuses those 15 archived HTML/goal pairs, but collects fresh DOM observations and uses
the actual configured Jev transport at execution. Preparation and pytest remain offline
with respect to the model. It allows at most one request and one host action per case,
with a shared 15-request / $0.05 cap, and stops on the first acceptance failure. The
approved run made four calls: three normal loops passed, then a safe `none` refusal
failed the frozen missing-identity category criterion; eleven cases remain unexecuted. Its
fixed `no_effect` case can pass only with the correct selection, one click, fresh
readback and the expected unknown result. New paid batches need separate approval.
This harness uses the plugin factory and task context directly; it is not another
Runner/YAML, global desktop-lock or native AX acceptance.

### Refusal behavior and category diagnostics

The current Controller prevents direct action for all four valid non-action controls,
then uses the same optional Advisor entry point. It does not currently branch on the
specific refusal category. The category descriptions and production prompt remain
unchanged; this observation does not remove their potential value for later planning.

The [prospective 11-case follow-up](../../benchmarks/computer_use/reports/20261003-s3-dom-followup-prepared/README.md)
separates verified no-action behavior from refusal-category matching in missing/conflict
cases. `none` and `escalate` can meet the primary zero-action criterion while remaining
explicit category misses. Incorrect actions, invalid responses, operational failures
and incorrect stale/no-effect behavior still stop the batch. This is a changed evaluator,
not demonstrated model improvement. The prior 3-pass/1-fail/11-not-run record is unchanged.

The approved follow-up made three calls: two missing-identity cases safely returned
`none` with category misses retained, then the toolbar conflict case clicked B and
reached its page postcondition. That action failed the predeclared conflict criterion,
so eight cases remain unexecuted. The result exposes that page-effect verification
alone does not establish identity-evidence consistency before dispatch. See the
follow-up record for the preserved 2-pass/1-fail/8-not-run outcome and limitations.

### Bounded generative selection and Jev fallback (S3)

Explicit browser configuration accepts `selector: llm` (rules then F/H3) or
`selector: jev-fallback` (rules then Jev, then F only after a valid non-action/J3).
The extension agent definition must name the approved text model with `model: <profile>`;
J3 also names its Jev profile with `decision-model: <profile>`. Existing `selector: jev`
and rule-only configurations retain their behavior. Production defaults are unchanged.

F borrows `context.runtime.model.complete`, receives the same semantic question and
whole action candidates as Jev, and may only return one offered ID/control. It creates
no client, tool loop, action arguments or new authority. Both calls use the original
context/usage/deadline. Each selector invocation permits at most one Jev and one F;
subsequent milestones return to normal host routing. Both refusing yields a controlled
stop; unavailable candidates/parameters remain outside this bounded selector's domain.
Unknown usage, invalid replies, revocation, cancellation and other hard stops propagate
without fallback. Stage/choice events expose routing without credentials.

The host text service permits only the optional fixed `extra_body: {enable_thinking:
false}` override for this comparison; other extra body/header overrides remain rejected.
The value is copied at assembly and passed to the SDK. This is not a
full planning/visual Advisor or S4 recovery implementation. See the
[strategy pilot protocol](../../benchmarks/computer_use/fixtures/s3-strategy/README.md).


### S3-M SDK migration and historical evidence

The current smoke, real-DOM and paired strategy harnesses use the core SDK service.
Older protocol/connection diagnostic replays retain a benchmark-only raw HTTP
client in `benchmarks/computer_use/legacy_json_model.py`; it is not a production
service or selectable plugin model. Their request/response parser exists solely
for historical replay semantics. Core never imports it.

Existing report directories and frozen digests are unchanged. A changed source
recipe requires a new freeze; use the recorded historical Git revision to reproduce
an old recipe. Old raw HTTP timing is not SDK timing. No new paid batch is needed
for the migration's fake-HTTP/Chromium acceptance. Candidate generation, milestone
schema v1, rule matching, four control results and explicit F fallback are unchanged;
S4 has not started.


### SDK call simplification (2026-10-05)

Current model-call captures use `capture_level: model_call` and `capture_status: returned`;
their request hash identifies normalized call parameters, not exact HTTP bytes.
Raw historical replays use a small experiment-only HTTP client and explicit admission
audit, without importing production route/transport machinery. Strict byte-level
protocol checks and three-phase wire audit are no longer production guarantees.
Historical artifacts are unchanged and require their recorded revision to reproduce.
The refactor does not change candidate generation, milestone v1 or F routing; S4
is not started.


Current experiment events are `model_request` / `model_response`, with
`capture_level: model_call`. `TaskModelCallRunner` and `ModelResponseStream` are core
implementation types, not additional plugin APIs. Jev receives no injected HTTP
client; normal creation/close and default environment handling belong to its SDK.
Old report files and their `sdk_*` labels are historical and are not rewritten.
