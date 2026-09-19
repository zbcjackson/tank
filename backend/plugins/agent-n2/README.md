# Navigator n2 agent

Tank plugin, not a general LLM provider. All GUI, shell and file operations
use the injected DesktopExecutor. Wire details follow the
[Yutori n2 reference](https://docs.yutori.com/reference/n2) (checked 2026-09-16).

Install from the backend workspace with `uv sync --package agent-n2` (or the
normal plugin installation flow). Merge `config.example.yaml` into the backend
configuration and set `YUTORI_API_KEY`. The factory resolves the configured
`llm_profile`; omitting it selects a profile named `agent-n2`.
Engine profiles are resolved by exact name, without falling back to the default
chat model. N2 requires `model: n2`; a missing profile or a different model fails
before screenshots or API calls. Do not omit the `agent_engines` mapping when
your profile is named `n2`.
The bundled `n2` definition uses background dispatch and a 300k
token budget. Dispatch through the existing `agent` tool and approve the task.
Screenshots of the entire desktop are sent to Yutori.

### macOS troubleshooting

If the log says `LLM profile 'agent-n2' not found`, check the file printed by
`Loaded config from ...` (normally `backend/core/config.yaml`). Merge both the
`llm.n2` profile and the top-level `agent_engines` mapping from
`config.example.yaml`, keeping the existing `llm.default` profile. Set
`YUTORI_API_KEY` in the backend environment, then restart the backend to ensure
the updated configuration and environment are loaded.

From `backend/core`, run `uv run tank-backend --check-computer-use` to check
macOS screen recording and accessibility permissions. Start a new Tank
conversation and type: “使用 n2 子 Agent 打开计算器，通过界面输入 7×8，读取显示结果。”
Approve the task. Expected logs include `N2 starting: profile=n2 model=n2`
and `N2 step ...: tools=['computer_batch']` (other returned tool names are also
logged). `AgentRunner ... finished` alone does not prove any desktop action.

DeepSeek notification errors mentioning `reasoning_content` are separate from
N2 desktop execution. Tank now preserves both native `reasoning_content` and
the compatible `reasoning` streaming field. Existing history that already lost
reasoning cannot be reconstructed by restarting. For DeepSeek flash/pro tool
requests, Tank now uses non-thinking mode when assistant history lacks reasoning,
logging the affected message indices while preserving the conversation. A new
conversation with complete reasoning follows the configured thinking behavior.
Langfuse/OTel connection failures at `localhost:3001` concern tracing and do not
establish whether N2 operated the desktop. Start the configured Langfuse service
or set `LANGFUSE_TRACING_ENABLED=false` and restart the backend for testing.

The plugin supports the 20260830 tool set, 15 batch primitives, normalized
coordinates without a second conversion, sequential key presses, modified
gestures, full message history and WebP screenshots. Every returned tool call
gets its own result. Edit requires a prior read/write of the same path; shell
calls invalidate those observations because cwd may change. Detached bash and
`replace_all` return explicit errors; use foreground bash or read/write instead.
File encoding follows the executor's UTF-8 contract. History is not compacted;
runs stop explicitly at max_steps or the request-size cap. Missing usage fails
the run so the worker's token budget cannot silently stop working.

## Development checks

From the repository root:

```sh
PYTHONPATH=backend/plugins/agent-n2 backend/.venv/bin/pytest backend/plugins/agent-n2/tests -q
backend/.venv/bin/ruff check backend/plugins/agent-n2
```

## T5 / A17 (dedicated GUI environment only)

1. Commit and push the implementation, then pull it on the dedicated GUI VM
   or macOS test machine. Install the plugin, apply the example configuration,
   restart Tank, and check that `agent-n2:agent` is registered.
2. Run `tank-backend --check-computer-use`. Enable recording/accessibility
   permissions on macOS and verify the screenshot/input channels.
3. Dispatch `n2` via `agent`: open an application, change a
   reversible setting, and perform a browser search. Check approval appears
   before dispatch, worker progress arrives, and final results are notified.
4. During a mouse-down / wait batch, call `agent_stop`; verify the worker is
   cancelled and no mouse button or modifier remains held.
5. Run the existing A17 harness with the same tasks, platform, resolution,
   trials and limits as Part A, changing only the agent to `n2`.
   Keep the trace and report as `n2-macos` / `n2-linux`; compare success rate,
   steps, elapsed time and token usage against the archived Part A report.

   From `backend/core`, after plugin installation:

   ```sh
   uv run --package agent-n2 python -m tank_backend.benchmarks --suite ../benchmarks/computer_use --agent n2 --trials 3 --label n2-macos
   ```

No real desktop actions are used in unit tests. A/B and T5 are pending until
the dedicated environment is run; plugin implementation does not prove n2's
task success rate.

The benchmark's per-trial isolation and scoring fixes are implemented; the
full three-way macOS comparison remains unverified. See the
[archived SDK migration design and N2 test guide](../../../docs/plans/done/plugin-subagents-and-n2-sdk.md)
for setup, dispatch, smoke commands, and measurement limits. The SDK path is
implemented; the existing engine and DesktopExecutor remain available.
Remaining macOS acceptance is tracked in the
[unified execution plan, S1–S4](../../../docs/plans/active/computer-use-adaptation-and-grounding.md).
