# Computer Use host loop — S0–S2 adapters

This opt-in `type: subagent` plugin uses the existing Runner/Adapter lifecycle.
It does not change the production computer-use agent or grounding modes.
The default factory currently has **no live channel or model transport**: a valid
goal returns `stopped / observation_unavailable`, with zero desktop/model calls.
Unknown private configuration keys are rejected. S1 provides injectable AX/OCR
observations; S2 adds explicitly configured managed Chromium. Native desktop
execution and Jev/Advisor domain wiring remain later stages.

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
