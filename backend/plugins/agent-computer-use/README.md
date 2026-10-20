# Computer Use host loop — S0–S4 adapters

This opt-in `type: subagent` plugin uses the existing Runner/Adapter lifecycle.
It does not change the production computer-use agent or grounding modes.
The default factory currently has **no live channel or model transport**: a valid
goal returns `stopped / observation_unavailable`, with zero desktop/model calls.
Unknown private configuration keys are rejected. S1 provides injectable AX/OCR
observations; S2 adds explicitly configured managed Chromium. S3 adds an opt-in Jev Choice
route, and S4 adds explicitly bound native macOS execution and an opt-in text planning Advisor.

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

`GoalContract` is the sole task input model, with `schema_version: 2`. It contains
intent/objective, goal identity and scope, the current task's authorization reference,
allowed operations, purpose-tagged inputs, optional outcomes/dependencies and completion
predicates. Version 1 and `milestones` are rejected; there is no legacy alias, converter,
separate parser or step-execution loop. See the example below.

The host builds complete click/fill candidates from the current observation and supplied
inputs. A single fill explicitly bound by its declared field label can use rules. Even a
single native form submit requires semantic selection: satisfied inputs do not prove its intent. Button-name
uniqueness alone does not prove action intent. Otherwise an explicitly configured selector
chooses a whole candidate. Parameters, native references, scope and observation bindings
remain host-owned. Missing evidence never establishes completion.

The Advisor may supplement only existing `source: generated` inputs whose value is absent,
choose an offered candidate, propose bounded planning focus, request observation, or report unable/needs-user-input.
Validated supplementation increments goal version while retaining authority, progress and
usage. It cannot replace existing values, remove completion conditions or widen scope.
The configured text Advisor uses the core task model. Open visual planning and natural-language
contract generation are not implemented.

Core TaskRuntime retains task-bound execution records and rechecks authority after async
preflight. Limits remain 32 action attempts, 64 observations and four Advisor calls;
unresolved effects permit up to three readbacks with short waits, never blind replay.
Repeated semantic state without a new verified action stops even with a fresh observation
ID. Revisiting a state after an action can request bounded Advisor recovery; it never repeats
the same selector choice blindly. Verified actions and
outcomes, native input bindings, receipts and pending effects are retained in progress.
Generic task resume is not implemented. The PDF fixture is synthetic and does not prove
filesystem output or overwrite protection.

`GoalProgress.recent_steps` retains the last ten admitted action attempts, numbered across
the task. Each records target semantics, input, selection source (`rules`, `selector`, or
`advisor`), before/after observation identity, separate dispatch/effect status, and observed
changes for the selected field or the candidate's readout/effect facts. A missing fact is
`null`, distinct from an observed empty string. Incomplete/not-ready observations do not
produce change evidence. The entry is created before dispatch, so exceptions/cancellation
cannot erase an attempted mutation. `not_sent` is distinct from an unresolved effect;
verified local effects still do not establish goal progress or task completion.

`model_view.py` is the shared, pure request projection for Jev, text selection and Advisor.
It exposes `state.recent_actions` without executable references or old action/observation
IDs, and replaces the model-facing verified-ID list with `verified_action_count`. Original
contracts and receipts stay host-owned. Every offered action receives a question-local
alias (`c1`, `c2`, ...), resolved against that call's original ActionSet after the response.
Original action IDs and malformed/unoffered aliases are not accepted as model choices.
Repeated readout baselines live in `state.value_change_checks`; candidate `change_refs`
point to them. These are local verification checks, not predicted effects or prior changes.
All candidates and their execution semantics remain available; target context and geometry
are retained. `computer_use_proposal` events tie the model alias and candidate-set identity
to the original action ID for receipt auditing. No new confidence gate is enabled.

With a configured selector, the Advisor may return `kind: focus` and a `focus` object with
an objective and one to eight exact fact completion conditions. This is planning guidance,
not native keyboard focus. The host accepts only known observation/goal/candidate-evidence
keys and rejects conditions already satisfied. It reobserves before returning to the selector;
the original goal, candidate set construction, authority and cumulative budgets remain intact.
Without a selector the model schema does not offer focus, and unsolicited focus is rejected.

`progress.current_focus` persists across observations for at most three admitted actions.
Verified focus completion clears it without completing the overall goal. Repeated states,
incomplete observations, changed goals, escalation and task termination invalidate it;
completion is checked before action expiry. Completed/invalidated records remain in
`focus_history`, bounded by the existing four-Advisor-call limit. Focus updates create a new
decision context but do not reset actual goal-progress, action, observation or model budgets.
The initial version supports exact fact predicates; it does not accept scripts, action IDs,
arbitrary tool parameters or unobservable free-text completion claims.

## Tests

From `backend/`, after installing the workspace plugin:

```bash
uv run --no-sync pytest plugins/agent-computer-use/tests -q
```

The existing `test/features/chat.feature` includes two isolated contracts for
this package. They complement the browser/WS suite; they do not claim live desktop
or real-model acceptance.

## S1 observation adapters

`AXObservationSource` reads a host-bound window/display without requiring a screenshot.
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

Configure the existing browser extension explicitly (the channel itself needs no model profile):

```yaml
subagents:
  agent-computer-use:agent:
    config:
      browser:
        scope: managed-page
        url: http://127.0.0.1:8080/form
        # frame_name: editor  # optional unique leaf frame
```

Without a configured selector, only an explicitly bound fill can run; a later submit stops
with partial progress. Configure Jev or F below to complete tasks that require click selection.

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

Supported action templates are button/link/native-checkbox click and editable textbox fill.
Names use aria-labelledby, aria-label, native labels or element text. This is a
bounded subset of DOM semantics, not a full accessible-name implementation.
Visible unique `role:label` observations produce facts with the current input
value or text content, e.g. `textbox:Name = 小明` and `status:Result = 小明`.
Goals must use these page predicates; a page message alone does not prove external
persistence or file creation. Duplicate keys supply no fact. DOM/node/text caps
and open shadow roots make the scope incomplete; loading documents are also incomplete.
Shadow DOM is not supported. The host-owned `status:Page URL` reports the real frame URL,
even if page text uses that label. Before capture, active Web Animations may settle
for at most 250ms; continuing animation refuses capture. No animation is disabled
and dispatch still compares exact PNG hashes.

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

Jev is a core-managed decision model. Core uses the official `typesafe-sdk==0.7.5`
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
Advisor declarations; outcome/completion predicates describe desired outcomes.
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

Compare the previous selector prompt with the current goal contract using the
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

Offline Jev image capability preparation is separate from this production loop.
Core decision profiles may opt in with `images: true`; supported fixed versions
are 1.13.0/1.14.0 for image Choice and 1.14.0 for Box. Both task image scope and
the specific Jev recipient opt-in are required. The SDK adds the experimental
header; capture/admission includes normalized JSON plus immutable raw file parts,
not base64 hidden in text. SDK 0.7.5 uploads multipart; services disable compression
and retries explicitly. Byte ceilings count compact parameters plus file bytes,
not HTTP framing/compression or provider re-encoding.

`JevImageProbe` captures a frame through the original runtime, normalizes EXIF
orientation/PNG/size/padding and retains its inverse mapping through M2 to screen
coordinates. It makes one image Choice or combined cardinality+Box call, then
rechecks a second capture from the same task/window/source observation. A stale
frame, revoked authority or unknown usage yields no evidence usable for progress.
The probe returns read-only evidence, has no executor and is not a factory
selector. No Box point is automatically dispatched, including `one` results;
confidence gates and real-application quality still need calibration/confirmation.
No-candidate Choice still cannot create an executable control. The new synthetic
[development recipe](../../benchmarks/computer_use/fixtures/jev-image-dev/README.md)
prepares input/label-separated task/stage specifications without SDK calls.

Explicit experimental `selector: jev-image` sends screenshots directly to an
image-enabled Jev decision profile and chooses only the original admitted actions.
It needs the host profile's `images: true` and task image scope; no separate visual
LLM is required. Images/candidate rectangles are normalized together and labeled
as attached-image pixels; the current execution path requires upright PNG sources.
Before submission it requires two identical captures within three attempts, then
retains the original native/DOM preflight and independent effect checks. Optional
`advisor: jev-image` reuses this path for bounded candidate review only, within the
original four-review cap; it cannot generate inputs, focus or arbitrary operations.
The advisor value requires this same selector. Existing selectors remain unchanged.
See the [real Calculator protocol](../../benchmarks/computer_use/fixtures/jev-image-native/README.md).

Explicit experimental `selector: jev-vision` replaces that text fallback with one
image-assisted choice among admitted actions. Declare `visual-model: <llm-profile>`
on the extension agent alongside `decision-model: <jev-profile>`. The host owns
both services. The visual profile declaration allows screenshots to that named
recipient; a supplied text-only `ModelDataScope` still refuses before capture.
Jev remains text-only. Default configuration is unchanged.

Complete observations and non-truncated executable candidates are required.
Unlabelled/generic labels or duplicate semantic identities bypass Jev text;
otherwise Jev gets the text question first. A valid Jev control output may take
over with a bound PNG and candidate image rectangles. Each repeated semantic
state permits one additional visual recovery. After verified effects, the next
host step reevaluates rules/text eligibility. Missing user facts, unavailable
images, stale references, malformed replies, unknown usage, cancellation,
revocation and limits never permit retry through another model. Unknown effects
retain readback-only handling.

Native capture crops the bound window using M2 `Observation`, maps AX bounds into
that image and rejects scene/geometry changes before input. Managed Chromium
captures its isolated main-frame viewport, without child frames. It checks pixels
before actionability trial, then DOM identity/navigation after the trial (which
may change hover pixels). The existing executor performs one selected action;
no coordinate invention, free-running agent or model completion claim is accepted.
Captures consume the original observation budget; SDK calls share its ledger and
deadline. Task closure releases images and clients. No legal candidates means no
visual action; canvas/Box coordinate execution remains pending. Tests use fake
models/native OS boundaries and real isolated Chromium, establishing wiring and
stops, not model quality.

Model captures and `model_call` events carry source purpose and unique call ID.
New summary `intake_calls` counts SDK invocations including failed intake;
`fallbacks` deduplicates those invocations by ID, not selection start/result pairs.
Correlated `started`/`finished` records distinguish actual SDK invocations from
policy/capture refusal (`not_started`, zero SDK calls). An unmatched start stays
missing (`null`); it is never inferred to be zero or a known invocation.
A legacy successful `details.intake` alone cannot establish attempts: intake is
missing (`null`), while available fallback starts count once. Stored historical
JSON and strict scoring are unchanged. Jev confidence, option probabilities and
candidate count are observable for later calibration; they do not drive routing.

Explicit browser configuration accepts `selector: llm` (rules then F/H3) or
`selector: jev-fallback` (rules then Jev, then F only after a valid non-action/J3).
The extension agent definition must name the approved text model with `model: <profile>`;
J3 also names its Jev profile with `decision-model: <profile>`. Existing `selector: jev`
and rule-only configurations retain their behavior. Production defaults are unchanged.

F borrows `context.runtime.model.complete`, receives the same semantic question and
whole action candidates as Jev, and may only return one offered ID/control. It creates
no client, tool loop, action arguments or new authority. Both calls use the original
context/usage/deadline. Each selector invocation permits at most one Jev and one F;
subsequent observations return to normal host routing. Both refusing yields a controlled
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
for the migration's fake-HTTP/Chromium acceptance. That S3-M migration preserved the then-current milestone contract. The subsequent
2026-10-07 goal unification removes that production path; current benchmark fixtures
use new goal-contract revisions, while archived results remain unchanged.


### SDK call simplification (2026-10-05)

Current model-call captures use `capture_level: model_call` and `capture_status: returned`;
their request hash identifies normalized call parameters, not exact HTTP bytes.
Raw historical replays use a small experiment-only HTTP client and explicit admission
audit, without importing production route/transport machinery. Strict byte-level
protocol checks and three-phase wire audit are no longer production guarantees.
Historical artifacts are unchanged and require their recorded revision to reproduce.
That model-call refactor did not change the then-current candidate generation or
F routing. The later goal-contract migration is a separate behavior change.


Current experiment events are `model_request` / `model_response`, with
`capture_level: model_call`. `TaskModelCallRunner` and `ModelResponseStream` are core
implementation types, not additional plugin APIs. Jev receives no injected HTTP
client; normal creation/close and default environment handling belong to its SDK.
Old report files and their `sdk_*` labels are historical and are not rewritten.


## S4 goal-driven contract (first slice)

With an explicitly configured browser and selector (`jev`, `llm` or `jev-fallback`),
`schema_version: 2` accepts an outcome without a predeclared click/fill script:

```json
{
  "schema_version": 2,
  "goal_id": "profile-name",
  "intent": "Save display name Ada; leave other profile fields unchanged",
  "objective": "Save display name Ada",
  "scope": "managed-page",
  "authorization_ref": "current_task",
  "allowed_operations": ["click", "fill"],
  "constraints": ["Leave other profile fields unchanged"],
  "inputs": [{"key": "name", "purpose": "profile display name",
              "value": "Ada"}],
  "completion": [{"key": "status:Saved name", "value": "Ada"}]
}
```

`current_task` references the already-granted task; it grants no permission. A known
matching task ID is also accepted. Optional input `field_scope` matches an observed named ancestor; when omitted,
candidates are bounded by the authorized page scope. Optional `field_label` narrows
it further, and `input_type` defaults to `text`.
Other native types require an explicit compatible declaration. Missing values
are never invented. Successful fills retain their native input binding. References include a document
instance identity, so a reload cannot transfer that binding to a new control.

The current DOM templates support navigation via `aria-controls` to a uniquely
named form/region/dialog, and native form submission once declared inputs are
observably satisfied. Same-origin, same-window non-download links may instead use
an exact destination-URL effect; blocked or redirected-to-other-URL navigation is
not verified. Uniquely named native checkboxes retain their checked-value effect.
Same-label native checkboxes instead use host-owned `dom:checked:` facts bound to
the actual node, so another same-name or replacement node cannot verify that effect.
Page-provided roles cannot supply these facts. A distinct authored form `name` is
shown literally as `[name=...]` for context. Missing/repeated names add no qualifier;
otherwise indistinguishable controls remain ambiguous.
Opaque readback keys never make checkbox targets semantically unique; collisions
between a name annotation and page labels also remain ambiguous. An image selector
can choose among the original bound candidates, without inventing a new action.
Controls without a supported effect template are excluded.
Controls inside native HTML table rows also include the row's visible text as
`row` ancestor context when the row has no authored accessible name. Hidden text
is excluded; repeated/empty context does not create a unique semantic identity.
The existing ancestor size limit and DOM/reference freshness checks still apply.
Completion requires `status:` facts; field values establish only local fill effects.
Optional `outcomes` add conjunctive result conditions and acyclic `depends_on`
references; they must all be verified as well as completion. No custom verification
code is executed. Textual constraints remain model context, not an arbitrary policy
language; scope, types, references and admitted capabilities are host-checked.

Each model question contains the current goal, snapshot, complete mixed actions,
input source keys, ancestors/current values and host progress. The host never executes a
button merely because its label is unique. More than 32 candidates or indistinguishable
candidates are rejected. A fresh observation follows each action; unverified effects
get at most three reads with short waits, then return unknown without replay. Repeated
semantic states stop even when observation IDs/generations change. The task shares
the existing 32-action/64-observation ceilings and model usage ledger.

Run the real Runner/SDK/Chromium control-chain acceptance (fake external model HTTP):

```bash
TANK_REQUIRE_CHROMIUM=1 uv run pytest plugins/agent-computer-use/tests/test_dom.py -k goal_runner -q
```

The fixture independently verifies its server-side saved name, unchanged email and
single save across two layouts and a normal intermediate page. This does not establish
real model competence, arbitrary-site support or authenticity of external business
receipts. Core same-process resume, Advisor supplementation/contract synthesis and
full S4 boundary acceptance remain pending. Production defaults are unchanged.


### Goal-contract migration and benchmark revisions (2026-10-07)

All executable callers use the sole `GoalContract`; no in-tree runtime v1 adapter is kept.
Existing reports retain their original evidence and digests. Current replay, holdout, DOM
and strategy inputs have new goal-contract revisions and must be frozen again before a
new authorized run. DOM runs read `fixtures/s3-dom/cases.json`, not goals extracted from
archived reports. Added public effect templates are synthetic fixture evidence, independent
of scoring labels; their resulting candidates and call counts are not the old S3 baseline.
The new replay revisions admit 72 model requests; the paired strategy recipe caps 81,
with per-task decision ceilings in its frozen cases. No new paid comparison was run.

## S4-AX: explicitly bound native macOS channel

Set `intake: llm` with `macos` to accept a natural-language `task` without a full GoalContract.
One call through the agent's configured text model returns a brief (application, objective,
inputs, completion types); the host expands it into a v2 contract, requires input values to
appear in the request text, and records the brief in result details. A full GoalContract in
`task_input` still bypasses intake. Browser configs cannot enable intake.

The `macos` config is a policy, not a window binding. Each task names its app in
`task_input.target: {application}` (bundle id or display name); the target never enters the
GoalContract shown to models. The host resolves the installed app, reuses the user's single
running instance or launches it, and binds its unique on-screen window; multiple instances or
windows stop with `needs_input`. Apps the plugin launched stay open and the user's apps are
never closed. `denied_bundles` and `blocked_terms` only extend the built-in lists.
PID lifetime is checked with Darwin kernel birth time and the executable bundle. Only a fully
visible primary-display window is supported. A new frontmost window of the same process is
followed; replacing the process, document, element or observation invalidates references.

Apps without readout-backed profiles use accessible names (or an explicit `labels` setting) and
no readouts. Their clicks are verified by a changed AX observation, and buttons whose labels
contain a danger term (send, delete, clear, 发送, 删除, … plus `blocked_terms`) lose click but
keep fill. Profiles that declare readouts skip the danger-term list because clicks carry local
value-change checks. Completion then uses
`ax:present:<name>`, `ax:absent:<name>` or `ax:title:<name>` conditions, judged against
the first complete observation of each window: a present value must be new and unique and
is matched on element values only.

Choose `dispatch: ax_press` or `dispatch: quartz` explicitly. Quartz uses the current AX
frame center, checks foreground/window exposure and refuses active user input. AX fill
uses a confirmed writable AXValue, preserving Unicode, whitespace and newlines. It never
silently switches to keyboard/clipboard input. Unknown dispatch effects are read back;
there is no retry using the other dispatch mode. Native work is joined before cleanup;
uncertain mouse release makes cleanup fail rather than reporting success.

`readouts` declare observable facts independently of a task's desired answers. Each names
an AX role and optional identifier/ancestor identifier. `single` preserves exact values;
`compact_text` combines static display text and removes whitespace/directional formatting
for mathematical readouts. `allow_empty` is limited to explicitly scoped static regions,
and at least one readout must require native evidence. Facts use `ax:value:<name>` keys.
With a profile, clicks carry a local value-change condition for these bound readouts, while
final completion still requires all declared goal predicates. UI changes are never completion.

For example, a policy with a Calculator profile can use:

```yaml
macos:
  blocked_terms: [archive]        # appended to the built-in danger terms
  profiles:
    com.apple.calculator:
      dispatch: ax_press
      readouts:
        - name: expression
          role: AXStaticText
          ancestor_identifier: StandardResultView
          aggregation: compact_text
          allow_empty: true
        - name: result
          role: AXStaticText
          ancestor_identifier: StandardInputView
          aggregation: compact_text
selector: jev
intake: llm
```

TextEdit uses `labels: identifier` and a single AXTextArea readout identified by
`First Text View`. This deliberately avoids its unavailable optional AXDescription;
other attribute failures still invalidate evidence. AXEnabled may be absent for a text
area whose AXValue is explicitly writable. Window chrome without semantic identity and
host `blocked_identifiers`/`blocked_labels` are not offered as actions. AX offers up to
64 complete candidates, without top-k truncation; the DOM default remains 32.

Normal pytest/Cucumber replaces OS and external HTTP boundaries. The dedicated native
pilot operates real newly owned Calculator/TextEdit windows with real Runner and SDK:

```bash
uv run python -m benchmarks.computer_use.s4_ax --output /tmp/new-ax-pilot
uv run python -m benchmarks.computer_use.s4_ax --output /tmp/new-ax-pilot --run fake --approved-sha256 <digest>
```

Preparation never touches the desktop or credentials. Fake mode installs a mock at the
SDK's actual httpx2 client boundary, disables environment proxies and uses a `.invalid`
endpoint. Live mode requires the matching frozen digest and configured TYPESAFE_API_KEY;
only that mode loads the real credential. The nine-case recipe covers Calculator AXPress
and Quartz three times each and TextEdit three times, including moved windows. It caps
78 decisions and estimated cost at $0.25 under its frozen Jev price contract. Any failed,
unknown, over-budget or cleanup-unconfirmed case stops the batch with remaining rows retained.

Independent readback traverses the bound AX window afresh, without consulting controller
snapshots or model answers. Calculator must show expression 7×8 and result 56; TextEdit
must contain the exact supplied text. Text entry does not claim a saved file. The pilot
refuses pre-existing target-app sessions and closes only its verified new process instance;
its temporary files are removed and foreground/position restoration is recorded. This is
not OS sandboxing, arbitrary-app coverage, background operation, or same-process resume.


Native AX decision requests use a compact model-only view: short question-local element
references, declared defaults for omitted element fields, and candidate properties read
through `target_ref`. Every action and control option remains present, and the returned
Choice key is still the original action ID. Execution snapshots, references and effect
checks are unchanged. This view applies to all-AX snapshots; DOM/fixture views keep their
existing representation. The model is explicitly instructed how to resolve references
and defaults. Task input strings and observed values are not rewritten.

Decision failures carry SDK error type, HTTP status and cause type as metadata; the task
emits `decision_error` before post-accounting stop checks can mask the original failure.
The native pilot saves these events with task/call IDs. It does not save SDK error messages,
response bodies or headers. Unknown usage still stops the batch; diagnostics do not bypass
budgets or enable retries.


## S4-R4 text Advisor and goal-progress review

Set `advisor: llm` alongside `browser` or `macos` and the desired selector. The extension
agent's existing `model: <profile>` supplies its core text model; `decision-model: <profile>`
continues to supply Jev. The plugin creates no model clients or separate budgets. Omitting
`advisor` leaves it disabled; neither this setting nor a model proposal grants permission.

```yaml
# Private extension config under subagents.agent-computer-use:agent.config
selector: jev
advisor: llm
# Include exactly one existing browser or macos binding here.
```

`LLMAdvisor` receives the goal, current structured observation/action set, progress, trigger
reason and parent task context. It returns one strict JSON object: an offered candidate ID,
a supported planning focus, values for declared missing generated inputs, `need_observation`, `needs_user_input` or
`unable`. Extra fields, duplicate JSON keys and mismatched kinds/fields are rejected. The
host validates goal patches and candidate membership, then uses the normal reference,
permission and effect gates. One proposal returns control to the host loop; no nested agent
or extra tools are installed. Known inputs cannot be overwritten; user-sourced missing
inputs return `missing_user_input`, without asking the Advisor to guess.

A verified local effect increments `unverified_goal_steps`. Newly satisfied declared
completion/outcome conditions or an exactly filled and bound goal input reset this counter;
each distinct piece of goal evidence counts once per task, so toggling it cannot repeatedly
reset the counter. Three actions without new goal evidence trigger `goal_progress_unverified`
before another ordinary selector call. This is a bounded planning-review trigger, not a
claim that every long task or changing value is incorrect. A single Advisor review permits
another bounded interval; it does not clear the evidence history, progress count, four-call
Advisor cap, or shared task/model/action/observation budgets. Without an Advisor it stops
with partial progress retained. Legitimate long tasks without intermediate predicates may
therefore need advice or additional declared outcomes.

Explicit `escalate` and action-induced repeated states can request advice. A selector's
`none` stops; `ambiguous`/`need_more_context` cause bounded read-only reobservation. Incomplete
observations are refreshed before invoking a configured Advisor; an unchanged repeat stops.
Pending/unknown effects never invoke planning to retry an uncertain action. The
`computer_use_advisor` events record reason, call number and source observation.

Offline acceptance uses real SDKs with fake model HTTP and native OS fixtures, plus real
isolated Chromium/Runner on two layouts and an intermediate page. It verifies Advisor→Jev
handoff and independently checks the persisted name and unchanged email. Scripted HTTP
answers establish control flow, not actual LLM planning quality. No new paid/native desktop
pilot has been run for this implementation; prior Calculator failures remain unchanged.

## G3 resource lifecycle and common acceptance (2026-10-17)

Supervised tasks may wait for one missing user value and continue the same coroutine,
runtime, grant, deadline and cumulative ledger. A new task receives a new runtime;
its completion cannot reopen the previous task or reuse its UI references. Task-bound
LLM views reject another task ID and inactive contexts before creating a client view.
The host owns its shared LLM pool; task-owned text/decision clients and browser resources
are closed with that task. Native app/window handles are borrowed; user apps are not
terminated by channel cleanup. The owned-app test harness has separate ownership.

From backend, run the common core entry:

```bash
uv run --no-sync pytest core/tests/test_subagent.py core/tests/test_task_model.py core/tests/test_task_runtime.py core/tests/test_plugin_manifest.py core/tests/test_model_calls.py -q
TANK_REQUIRE_CHROMIUM=1 uv run --no-sync pytest plugins/agent-computer-use/tests/test_dom.py -q
```

The existing chat.feature lifecycle case runs the core entry. The DOM cases include
two consecutive tasks on one Runner with disjoint document references and independent
server readback. See the [capability/resource inventory](../../../docs/design/computer-use.md#g3-能力与资源接线清单2026-10-17)
and [current native fake-GUI/Vision evidence](../../benchmarks/computer_use/reports/20261017-g3-resource-native-fake/README.md).
These validate host wiring and ownership, not real-model accuracy or adoption.
OCR/fusion remain read-only injectable adapters with no default factory switch;
open visual planning, automatic OCR fallback, Box coordinate execution and persistent cross-process
resume are not enabled by this work. Production defaults remain unchanged.
