"""Shell hook system — user-defined scripts that fire on tool lifecycle events.

Reads the ``hooks:`` block from config.yaml, runs shell scripts on
``pre_tool_call`` and ``post_tool_call`` events. Scripts receive JSON
on stdin and can optionally return JSON on stdout to block execution
or inject context.

Design (modeled on Hermes Agent ``shell_hooks.py``):
- Config-driven: ``hooks:`` block in YAML defines event + command + matcher
- Wire protocol: JSON on stdin, optional JSON on stdout
- Pre-tool hooks can ``{action: "block", reason: "..."}`` to prevent execution
- Post-tool hooks are fire-and-forget (observability only)
- Timeout protection: scripts killed after configurable timeout
- Consent not yet implemented (Phase 4.5)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shlex
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookSpec:
    """A single hook definition from config."""

    event: str  # "pre_tool_call" | "post_tool_call" | "pre_llm_call"
    command: str  # Shell command to run
    matcher: str = ""  # Regex pattern for tool name (empty = all tools)
    timeout: float = 5.0  # Seconds before killing the subprocess
    enabled: bool = True


@dataclass(frozen=True)
class HookDecision:
    """Result from a pre_tool_call hook."""

    blocked: bool = False
    reason: str = ""

    @classmethod
    def allow(cls) -> HookDecision:
        return cls(blocked=False)

    @classmethod
    def block(cls, reason: str) -> HookDecision:
        return cls(blocked=True, reason=reason)


class HookManager:
    """Manages and executes lifecycle hooks.

    Instantiated once at startup. The manager is called by the tool
    execution path (in ``llm.py`` or ``ApprovalGateExecutor``).
    """

    def __init__(self, hooks: list[HookSpec] | None = None) -> None:
        self._hooks = hooks or []
        self._matchers: dict[str, Any] = {}
        self._compile_matchers()

    @classmethod
    def from_config(cls, config: Any) -> HookManager:
        """Build from a HooksConfig dataclass."""
        if config is None or not getattr(config, 'hooks', None):
            return cls(hooks=[])
        specs = []
        for h in config.hooks:
            specs.append(HookSpec(
                event=h.event,
                command=h.command,
                matcher=h.get('matcher', ''),
                timeout=h.get('timeout', 5.0),
                enabled=h.get('enabled', True),
            ))
        return cls(hooks=specs)

    def _compile_matchers(self) -> None:
        """Pre-compile regex matchers for tool name filtering."""
        import re

        for hook in self._hooks:
            if hook.matcher:
                try:
                    self._matchers[id(hook)] = re.compile(hook.matcher)
                except re.error:
                    logger.warning(
                        "Invalid hook matcher regex: %s", hook.matcher,
                    )

    def _matches_tool(self, hook: HookSpec, tool_name: str) -> bool:
        """Check if a hook's matcher applies to this tool name."""
        if not hook.matcher:
            return True  # Empty matcher = all tools
        compiled = self._matchers.get(id(hook))
        if compiled is None:
            return False
        return compiled.search(tool_name) is not None

    def get_hooks_for_event(
        self, event: str, tool_name: str = "",
    ) -> list[HookSpec]:
        """Return all enabled hooks matching an event and tool name."""
        return [
            h for h in self._hooks
            if h.enabled and h.event == event
            and self._matches_tool(h, tool_name)
        ]

    async def run_pre_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        session_id: str = "",
        cwd: str = "",
    ) -> HookDecision:
        """Run all pre_tool_call hooks. First block wins.

        Returns HookDecision.allow() if no hook blocks.
        """
        hooks = self.get_hooks_for_event("pre_tool_call", tool_name)
        if not hooks:
            return HookDecision.allow()

        payload = {
            "hook_event_name": "pre_tool_call",
            "tool_name": tool_name,
            "tool_input": tool_args,
            "session_id": session_id,
            "cwd": cwd or os.getcwd(),
        }

        for hook in hooks:
            result = await self._execute_hook(hook, payload)
            if result is not None and result.get("action") == "block":
                reason = result.get("reason") or result.get("message") or "blocked by hook"
                logger.info(
                    "Hook blocked tool call: %s — %s",
                    tool_name, reason,
                )
                return HookDecision.block(reason)

        return HookDecision.allow()

    async def run_post_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        result_content: str = "",
        error: bool = False,
        *,
        session_id: str = "",
    ) -> None:
        """Run all post_tool_call hooks (fire-and-forget, no blocking)."""
        hooks = self.get_hooks_for_event("post_tool_call", tool_name)
        if not hooks:
            return

        payload = {
            "hook_event_name": "post_tool_call",
            "tool_name": tool_name,
            "tool_input": tool_args,
            "result": result_content[:2000],  # Truncate large results
            "error": error,
            "session_id": session_id,
        }

        for hook in hooks:
            # Fire-and-forget — don't let failures affect the main flow
            try:
                await self._execute_hook(hook, payload)
            except Exception:
                logger.debug(
                    "Post-tool hook error (ignored): %s", hook.command,
                    exc_info=True,
                )

    async def _execute_hook(
        self, hook: HookSpec, payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Execute a single hook script.

        Passes payload as JSON on stdin. Returns parsed JSON from stdout,
        or None if the script produces no JSON output.
        """
        try:
            argv = shlex.split(os.path.expanduser(hook.command))
        except ValueError as e:
            logger.warning("Failed to parse hook command '%s': %s", hook.command, e)
            return None

        stdin_data = json.dumps(payload, ensure_ascii=False).encode()

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=hook.timeout,
            )

            if proc.returncode != 0:
                logger.debug(
                    "Hook '%s' exited %d: %s",
                    hook.command, proc.returncode,
                    stderr.decode(errors="replace")[:200],
                )
                return None

            # Parse stdout as JSON (optional — scripts may produce no output)
            stdout_text = stdout.decode(errors="replace").strip()
            if not stdout_text:
                return None

            try:
                return json.loads(stdout_text)
            except json.JSONDecodeError:
                logger.debug(
                    "Hook '%s' stdout not JSON: %s",
                    hook.command, stdout_text[:100],
                )
                return None

        except asyncio.TimeoutError:
            logger.warning(
                "Hook '%s' timed out after %.1fs — killed",
                hook.command, hook.timeout,
            )
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            return None

        except FileNotFoundError:
            logger.warning("Hook command not found: %s", argv[0])
            return None

        except Exception:
            logger.warning(
                "Hook '%s' failed unexpectedly", hook.command, exc_info=True,
            )
            return None
