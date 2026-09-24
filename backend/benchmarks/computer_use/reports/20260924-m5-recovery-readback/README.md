# M5 desktop recovery readback correction

Date: 2026-09-24. Status: local normal, hard-exit and timeout recovery acceptance
passed; no model requests or screenshots. This supersedes the prior inference
that a loginwindow frontmost-app reading proved the user was on a locked desktop.
The user explicitly confirmed the desktop was normal. The historical reason for
that reading is not established; it must not be presented as confirmed lock state.

## Findings and changes

A fresh read of NSWorkspace and System Events agreed on the normal conversation
app. Replaying recovery then exposed stale state: a later fresh process confirmed
visibility restoration although the immediate check failed. The prior Calculator
close check also gave a false positive: its cached running-app list omitted the
Calculator launched by the child. The leftover instance was identified by launch
time as belonging to the probe and closed before further trials.

[Apple documents](https://developer.apple.com/documentation/appkit/nsrunningapplication?language=objc)
that mutable NSRunningApplication properties update as the main run loop runs.
The supervisor now pumps that loop before baseline/readback and uses bounded
(two-second) event-loop waits after close, hide/unhide and activation requests.
A persistent unavailable/loginwindow foreground produces an inability-to-capture
error after refreshing; this is not called a lock-state diagnosis.

Finder on this host returned no AppKit launchDate. The previous code silently
omitted it from the baseline and therefore could not restore it as the foreground
app. Capture now retains those applications using `ps -p PID -o lstart=` as an
identity fallback. Restoration checks PID, bundle and the same identity source;
a different launch time is rejected before hide/unhide/activation.

## Real local acceptance

Each child changed the clipboard, moved the pointer, hid the original front app
when applicable, opened Calculator, pinned English and posted Shift-down. The
outer supervisor retained its private baseline and performed recovery after:

- Normal exit: code 0, timeout=false, all seven recovery fields true.
- Hard exit: SIGKILL/code -9, timeout=false, all seven recovery fields true.
- Timeout: supervisor killed/reaped the child after four seconds, code -9,
  timeout=true, all seven recovery fields true.

The seven checks are inputs released, Calculator closed, original app visibility,
clipboard, cursor, original foreground app and input source. result.json files
are copied unchanged. No private baseline, clipboard payload or application
inventory is archived. Earlier failed results are retained separately, not relabeled.
The three failures preserve what the old check reported; their true fields do not
retroactively establish correctness where later stale-cache evidence contradicted it.

These are controlled local process-recovery tests. They do not reproduce the
historical native IME SIGTRAP, prove model task accuracy, certify user-concurrent
input, supervisor death/power-loss recovery, or complete the M6 stop matrix.

## Tests and next step

Five additional unit cases cover stale foreground refresh, delayed visibility
updates, permanently failed visibility restoration, Finder's missing launchDate,
and PID reuse with changed start time. Main/native boundaries are fake in those
cases; real child processes/files/signals remain covered by the earlier tests.

Full mandatory verification passed: backend 5036 passed / 1 skipped, E2E
16 scenarios / 63 steps, web lint/TypeScript, backend/CLI Ruff, changed-file
Pyright, dev-server error check, docs consistency and protocol sync. Before
another paid B trial, regenerate the source freeze/proposal and prepare a preview
under the outer recovery owner. Existing consumed one-trial authorizations are
not reused. This local acceptance sends no desktop images to a model endpoint.
