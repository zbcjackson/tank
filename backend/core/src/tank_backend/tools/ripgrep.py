"""ripgrep subprocess runner — find and invoke rg for fast file search."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Constants matching Claude Code's approach
TIMEOUT_SECONDS = 20
MAX_STDOUT_BYTES = 20 * 1024 * 1024  # 20 MB
DEFAULT_HEAD_LIMIT = 250

# rg exit codes
_EXIT_MATCH = 0
_EXIT_NO_MATCH = 1
_EXIT_ERROR = 2

# VCS dirs to always exclude
_VCS_EXCLUDES = ("!.git", "!.svn", "!.hg", "!.bzr", "!.jj")

# EAGAIN detection
_EAGAIN_MARKERS = ("os error 11", "Resource temporarily unavailable")


@dataclass(frozen=True)
class RipgrepResult:
    """Parsed result from a ripgrep invocation."""

    lines: list[str] = field(default_factory=list)
    truncated: bool = False
    exit_code: int = 0
    error: str | None = None


# ------------------------------------------------------------------
# Binary discovery
# ------------------------------------------------------------------

def find_rg_binary() -> str | None:
    """Locate the ``rg`` binary. Returns absolute path or ``None``."""
    found = shutil.which("rg")
    if found:
        return found
    for candidate in (
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
        "/usr/bin/rg",
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# ------------------------------------------------------------------
# Argument builder
# ------------------------------------------------------------------

def build_rg_args(
    pattern: str,
    *,
    output_mode: str = "content",
    glob: str | None = None,
    file_type: str | None = None,
    case_insensitive: bool = False,
    multiline: bool = False,
    context_before: int = 0,
    context_after: int = 0,
    context: int = 0,
    line_numbers: bool = True,
    fixed_strings: bool = False,
) -> list[str]:
    """Build the ``rg`` argument list from search parameters.

    Does NOT include the search path — caller appends that.
    """
    args: list[str] = [
        "--no-heading",
        "--with-filename",
        "--color=never",
        "--hidden",
        "--max-columns=500",
    ]

    # Exclude VCS directories
    for vcs in _VCS_EXCLUDES:
        args.extend(("--glob", vcs))

    # Output mode
    if output_mode == "files_with_matches":
        args.append("--files-with-matches")
    elif output_mode == "count":
        args.append("--count")
    else:
        # content mode
        if line_numbers:
            args.append("--line-number")

    # Context (only meaningful for content mode)
    if output_mode == "content":
        if context > 0:
            args.extend(("-C", str(context)))
        else:
            if context_before > 0:
                args.extend(("-B", str(context_before)))
            if context_after > 0:
                args.extend(("-A", str(context_after)))

    # Filters
    if glob:
        args.extend(("--glob", glob))
    if file_type:
        args.extend(("--type", file_type))
    if case_insensitive:
        args.append("-i")
    if multiline:
        args.extend(("--multiline", "--multiline-dotall"))
    if fixed_strings:
        args.append("--fixed-strings")

    # Pattern
    args.extend(("-e", pattern))

    return args


# ------------------------------------------------------------------
# Subprocess execution
# ------------------------------------------------------------------

def _is_eagain(stderr: str) -> bool:
    """Detect EAGAIN / resource-temporarily-unavailable in stderr."""
    lower = stderr.lower()
    return any(marker in lower for marker in _EAGAIN_MARKERS)


def run_rg_sync(
    rg_binary: str,
    args: list[str],
    path: str,
    *,
    timeout: int = TIMEOUT_SECONDS,
    _retry: bool = False,
) -> RipgrepResult:
    """Blocking ripgrep call — designed for ``asyncio.to_thread``.

    Handles timeout, buffer limits, and EAGAIN retry with ``-j 1``.
    """
    full_args = [rg_binary, *args, path]

    try:
        proc = subprocess.run(
            full_args,
            capture_output=True,
            timeout=timeout,
            text=False,  # raw bytes for buffer control
        )
    except subprocess.TimeoutExpired as exc:
        # Return partial output if available
        stdout = (exc.stdout or b"")[:MAX_STDOUT_BYTES]
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        # Drop last line — may be incomplete
        if lines:
            lines = lines[:-1]
        return RipgrepResult(
            lines=lines,
            truncated=True,
            exit_code=-1,
            error=f"ripgrep timed out after {timeout}s",
        )
    except FileNotFoundError:
        return RipgrepResult(
            exit_code=-1,
            error=f"ripgrep binary not found: {rg_binary}",
        )
    except OSError as exc:
        return RipgrepResult(exit_code=-1, error=str(exc))

    stdout = proc.stdout[:MAX_STDOUT_BYTES]
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""

    # EAGAIN retry (once)
    if not _retry and _is_eagain(stderr):
        logger.warning("ripgrep EAGAIN — retrying with -j 1")
        retry_args = ["-j", "1", *args]
        return run_rg_sync(
            rg_binary, retry_args, path, timeout=timeout, _retry=True,
        )

    if proc.returncode == _EXIT_ERROR:
        return RipgrepResult(
            exit_code=_EXIT_ERROR,
            error=f"ripgrep error: {stderr.strip()}",
        )

    text = stdout.decode("utf-8", errors="replace")
    lines = text.splitlines() if text.strip() else []
    truncated = len(proc.stdout) >= MAX_STDOUT_BYTES

    return RipgrepResult(
        lines=lines,
        truncated=truncated,
        exit_code=proc.returncode,
    )


# ------------------------------------------------------------------
# Async entry point with pagination
# ------------------------------------------------------------------

async def run_ripgrep(
    rg_binary: str,
    pattern: str,
    path: str,
    *,
    output_mode: str = "content",
    glob: str | None = None,
    file_type: str | None = None,
    case_insensitive: bool = False,
    multiline: bool = False,
    context_before: int = 0,
    context_after: int = 0,
    context: int = 0,
    line_numbers: bool = True,
    fixed_strings: bool = False,
    head_limit: int = DEFAULT_HEAD_LIMIT,
    offset: int = 0,
    timeout: int = TIMEOUT_SECONDS,
) -> RipgrepResult:
    """Async ripgrep search with pagination.

    Runs ``rg`` via ``asyncio.to_thread``, then applies
    ``offset`` / ``head_limit`` to the output lines.
    """
    args = build_rg_args(
        pattern,
        output_mode=output_mode,
        glob=glob,
        file_type=file_type,
        case_insensitive=case_insensitive,
        multiline=multiline,
        context_before=context_before,
        context_after=context_after,
        context=context,
        line_numbers=line_numbers,
        fixed_strings=fixed_strings,
    )

    result = await asyncio.to_thread(
        run_rg_sync, rg_binary, args, path, timeout=timeout,
    )

    if result.error:
        return result

    # Apply pagination
    lines = result.lines
    if offset > 0:
        lines = lines[offset:]
    truncated = result.truncated
    if head_limit > 0 and len(lines) > head_limit:
        lines = lines[:head_limit]
        truncated = True

    return RipgrepResult(
        lines=lines,
        truncated=truncated,
        exit_code=result.exit_code,
    )
