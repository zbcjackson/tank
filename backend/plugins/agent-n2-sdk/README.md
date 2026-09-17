# Navigator n2 SDK subagent

Tank's `n2_sdk` definition runs the official `N2ComputerAgent` through the generic
`SubAgent` contract, WorkerSupervisor and AgentRunner. The existing `n2` engine
remains available. This plugin never uses Tank's DesktopExecutor or implements
an N2 prediction/tool loop.

## Install and select

From `backend/`, install the workspace packages needed by the server:

```bash
uv sync --all-packages --all-groups
uv run --no-sync pytest plugins/agent-n2-sdk/tests -q
```

The dependency is pinned to `yutori[macos]==0.9.29`; the macOS extra installs
`cua-driver==0.23.2` only on Darwin. Core modules do not import yutori. Restart
the backend to discover the new `agent-n2-sdk:agent` manifest. Verify that the
plugin and extension are enabled in `core/plugins.yaml` and that `agents.dirs`
includes `../agents`. The existing directory loader already discovers
`agents/n2-sdk.md`; no additional Brain catalog is necessary.

Set `YUTORI_API_KEY` in `backend/core/.env` or the server's environment. The main
`core/config.yaml` contains the separate `subagents` entry. The example file is
for reference, not automatically merged. No additional LLM profile is required
for this plugin. For a test dispatch explicitly request **n2_sdk**:

```json
{"subagent_type":"n2_sdk","prompt":"用 GUI 打开计算器，计算 7×8，确认显示 56。","run_in_background":true}
```

The user approves the whole desktop/shell/filesystem/network scope before any
environment starts. These grants authorize trusted code on a dedicated desktop;
they are not a sandbox or directory/network isolation. Existing Tank tool
allowlists and LLM profiles do not constrain tools inside this SDK. Use OS/VM
isolation when such limits are required. Model calls upload desktop screenshots.

## Platform and capability boundary

| Platform | Environment | Status |
|---|---|---|
| macOS | Official MacOSComputer, single-screen desktop scope | Implemented; real desktop acceptance pending |
| Linux X11 | No adapter enabled | Explicitly unsupported until separate acceptance |
| Linux Wayland / other OS | No adapter | Explicitly unsupported |

The default macOS transport requires **CuaDriver.app** in addition to the Python
wheel. Its MCP subprocess proxies to the app's daemon; macOS attributes Screen
Recording and Accessibility permissions to that app. Granting permissions only
to Terminal/Python does not establish readiness for this launch mode. Install the
matching pinned standalone app on the Mac, then check it before dispatch:

```bash
# From backend/; install the same driver release as the Python dependency.
curl -fL https://github.com/trycua/cua/releases/download/cua-driver-rs-v0.23.2/install.sh \
  -o /tmp/tank-cua-driver-install.sh
CUA_DRIVER_RS_VERSION=0.23.2 bash /tmp/tank-cua-driver-install.sh
open -n -g -a CuaDriver --args serve
uv run --no-sync cua-driver permissions grant
uv run --no-sync cua-driver permissions status
uv run --no-sync cua-driver doctor
```

Confirm both permissions in macOS System Settings for CuaDriver.app. Read the
doctor findings even if its exit code is zero. These steps follow the driver's
[pinned launch contract](https://github.com/trycua/cua/blob/cua-driver-rs-v0.23.2/libs/cua-driver/README.md#macos-process-identity-and-permissions).
Tank does not install the app or change OS permissions during dispatch.

The SDK starts and owns a persistent `cua-driver mcp` proxy subprocess for each
environment; the standalone daemon may be shared and is not owned by the worker.
Worker cleanup ends its session and closes the proxy. Overlay presentation is disabled.
Modified clicks are enabled; modified scroll is explicitly disabled because the
pinned MacOSComputer refuses it. Coordinates delivered to this adapter are pixels;
the SDK performs normalization/denormalization itself.

The pinned native adapter emulates held mouse/key state and delivers atomic
click/drag/key gestures; it does not provide a continuously held physical input
between separate primitives. Do not interpret fake tests as proof of physical
hold/drag cancellation or GUI task success. These limitations must be checked
against actual task needs during M6. No Linux cancellation capability is claimed.

`cancel=true` exposes the existing cooperative `agent_stop` path. Pause, resume
and persistent resume remain false. `agent_status` inspects the persisted worker.
Task cancellation reaches the SDK CancellationLatch and producer task; producer
shutdown precedes SDK, environment and injected client cleanup. Unconfirmed
cleanup fails the worker and quarantines the same-process desktop resource.
An operator can call `DESKTOP_RESOURCE.clear_quarantine()` only after verifying
that input and owned processes have been released; there is no automatic reset.
The lock covers Runner-managed computer_use/n2/n2_sdk tasks in one event loop,
not direct main-session tools or separate benchmark processes.

## Accounting and outcomes

Every returned API response, including compaction and SDK format/length retries,
is counted once by the completions wrapper. SDK usage callbacks never add tokens
again. The ledger works without an observer. Each request and adapter primitive
checks authorization, cancellation, budget and deadline. A response can exceed
the token threshold; no subsequent action is started. Missing usage stops the
run, while an interrupted request records unknown usage instead of known zero.
Client-internal transport retries are reported as one logical call.

SDK `max_steps` limits model turns. Benchmark `max_steps` separately limits begun
tool calls in the start callback. Batch primitive count is a diagnostic. Only
explicit `final_answer` followed by confirmed cleanup completes a worker;
budget/max_steps/context_limit/unknown endings fail it. Exceptions fail, deadlines
time out and acknowledged cancellation cancels. Completed does not prove the
business result: inspect side effects or use validators.

## Verification

Contract and plugin tests use the actual pinned SDK with fake environments and
completions; they perform no paid API requests or host input. Cucumber scenarios
in the existing `test/features/chat.feature` run an isolated fake SDK process
through actual AgentTool/ConfirmActionTool, Supervisor, Runner, WorkerStore,
status/stop tools, NotificationHub and the existing WebSocket frame converters.
They cover denial, approval/background completion, cancellation and API failure.
The live client transport is covered separately by the existing E2E scenarios.

Real macOS acceptance, physical input/process cleanup and same-machine A/B
reports are still required by the
[implementation plan](../../../docs/plans/active/plugin-subagents-and-n2-sdk.md).
Run benchmark trials serially with other desktop automation stopped:

```bash
cd core
uv run --no-sync python -m tank_backend.benchmarks --help
```

Sources: [pinned release](https://pypi.org/project/yutori/0.9.29/),
[official SDK](https://github.com/yutori-ai/yutori-sdk-python),
[N2 reference](https://docs.yutori.com/reference/n2). SDK upgrades require contract
and lifecycle regression tests before changing the pin.
