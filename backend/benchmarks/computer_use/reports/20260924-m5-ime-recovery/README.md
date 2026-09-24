# M5 IME isolation and desktop recovery

Date: 2026-09-24. Status: IME isolation locally verified; complete desktop recovery
acceptance pending an unlocked interactive desktop. Zero model requests or screenshots.

## IME isolation

The historical B-protocol-only SIGTRAP was not reproduced by minimal lookup-only
main/worker-thread probes, including after AppKit initialization. These probes
use the pre-change ime module; their source snapshots are historical, not a new
reproduction recipe against the changed API. Queue affinity remains a plausible
trigger, not a fully established sufficient cause.

All benchmark Carbon calls now run on a short-lived helper process's main thread.
The parent checks exit status, response shape and a 5-second timeout; native abort
cannot kill the parent that owns desktop restoration. Saved input sources are IDs,
not process-local CF pointers. Failed restoration retains the original ID for retry.
No production computer-use budget or tool schema changed.

A real worker-thread test saved the input source, pinned English five times and
restored it with matching readback (five pin calls total 0.362 seconds). The actual
RepinImeAfterLaunchTool / LaunchAppTool path launched Calculator, Finder, Calculator;
all three readbacks were ABC. Original front app and input source restoration were
confirmed at that point. No screenshot or model was used.

## Outer recovery owner

`backend/scripts/supervise_computer_pilot.py` runs a supplied controlled launcher
under a separate parent. The existing launcher's model authorization and freeze
gates still apply. It does not authorize or resume any model trial.

Before releasing the child to execute, the supervisor fsyncs a baseline and child
PID in a new private directory (0700, files 0600). It waits outside the launcher,
stops/reaps it on timeout and attempts input release, Calculator close, application
visibility, clipboard, cursor, front app and input-source restoration independently.
A failure produces confirmed=false. Existing Calculator sessions and loginwindow
are refused before launch. Baseline files contain private clipboard/app state and
must stay local; they are deliberately excluded from these artifacts.

The real hard-exit probe changed clipboard/cursor, hid the front application,
opened Calculator, pinned English and posted Shift-down, then killed itself.
The outer owner confirmed input release, Calculator close, app visibility,
clipboard, cursor and input-source restoration. Front restoration failed; the raw
result remains confirmed=false. Investigation found the original front process
was loginwindow (an accessory app), absent from the initial regular-app inventory.
The code now includes accessory front identities and rejects loginwindow upfront.
A follow-up attempt was refused because Calculator was present, without starting
a child. Full acceptance remains pending an unlocked, idle desktop with Calculator
closed. No claim is made that this failure was fixed by unit tests alone.

The supervisor itself being killed, machine failure, applications terminating or
user changes during the run are not certified. Durable baseline files allow local
inspection/recovery; automatic restart after supervisor death is not implemented.
The source snapshot of the desktop probe uses its retry directory; the first raw
result comes from the preceding equivalent probe before the directory suffix change.

## Tests

New tests exercise subprocess-main-thread lifecycle, SIGKILL, timeout, malformed
responses, failed restoration retry, durable baseline-before-execution ordering,
private file modes, child reaping, write failure, recovery failure, accessory front
capture and loginwindow refusal. Native boundaries are faked in unit tests; real
processes/files/signals are used for process-lifecycle checks.

Verification passed: backend 5031 passed / 1 skipped (16 new cases), E2E 16
scenarios / 63 steps, web lint/TypeScript, backend/CLI Ruff, changed-file Pyright,
dev-server error check, docs consistency and protocol sync. Initial sandbox-only
loopback/tmux/uv restrictions were resolved by rerunning with local permissions.
No failed tests remain. Physical recovery acceptance is still pending as above.
The old runtime/proposal source hashes are stale after this change; rebuild and
review new preparation artifacts before any new paid trial. Previous one-trial
screenshot authorizations are not extended by this work.
