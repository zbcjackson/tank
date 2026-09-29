# Computer Use host loop — S0 offline implementation

This opt-in `type: subagent` plugin uses the existing Runner/Adapter lifecycle.
It does not change the production computer-use agent or grounding modes.
The default factory currently has **no live channel or model transport**: a valid
goal returns `stopped / observation_unavailable`, with zero desktop/model calls.
Unknown private configuration keys are rejected. Do not enable it expecting a
working desktop agent; real AX/OCR/DOM and HTTP budget wiring are later batches.

The constructor accepts separate observation, action, selector and Advisor
implementations. Tests inject semantic fake UI boundaries through the actual
registry, AgentTool, approval, Supervisor, Runner and SQLite path. Owned resources
are registered with the core task runtime; the generic adapter joins cleanup and
quarantines the desktop on unconfirmed cleanup. Core cleanup also handles an
unstarted plugin, attempts other releases after one fails, and shares the outcome
across repeated close calls. Cancellation retains already-journaled effects.

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
protection, native identities and application-specific evidence are **not**
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

Selector/Advisor are offline injection seams only. No implementation here opens
HTTP, so this does **not** establish model budget reservation, SDK serialization,
usage settlement or paid experiment admission. Existing benchmark rejection of
unwired extension transports remains in place.

## Tests

From `backend/`, after installing the workspace plugin:

```bash
uv run --no-sync pytest plugins/agent-computer-use/tests -q
```

The existing `test/features/chat.feature` includes two isolated contracts for
this package. They complement the browser/WS suite; they do not claim live desktop
or real-model acceptance.
