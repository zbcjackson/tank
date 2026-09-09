"""Async shell execution for task setup/validator scripts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


class ShellError(Exception):
    """A shell command failed (non-zero exit, or timeout)."""

    def __init__(self, message: str, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class ShellResult:
    returncode: int
    stdout: str
    stderr: str


async def run_shell(
    command: str, *, timeout_s: float, extra_env: dict[str, str] | None = None
) -> ShellResult:
    """Run ``bash -c <command>`` and capture combined output.

    ``extra_env`` adds variables (e.g. ``BENCH_CAPTURE``) on top of the
    inherited environment. Raises ``ShellError`` on non-zero exit or
    timeout.
    """
    import os

    env = {**os.environ, **extra_env} if extra_env else None
    proc = await asyncio.create_subprocess_exec(
        "bash", "-c", command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise ShellError(
            f"command timed out after {timeout_s}s: {command[:120]}",
            returncode=-1, stdout="", stderr="timeout",
        ) from e

    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")
    returncode = proc.returncode if proc.returncode is not None else -1
    if returncode != 0:
        raise ShellError(
            f"command failed (exit {returncode}): {command[:120]}\n"
            f"stdout: {stdout[-500:]}\nstderr: {stderr[-500:]}",
            returncode=returncode, stdout=stdout, stderr=stderr,
        )
    return ShellResult(returncode=returncode, stdout=stdout, stderr=stderr)
