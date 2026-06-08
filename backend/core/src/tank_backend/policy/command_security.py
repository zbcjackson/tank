"""Command security policy — evaluate allow/require_approval/deny per shell command.

Three-layer evaluation:
1. Dangerous patterns (regex) — hard-block destructive constructs (DENY)
2. Safe command allowlist — known-safe base commands auto-approve (ALLOW)
3. Unknown commands — require approval or optional LLM evaluation (REQUIRE_APPROVAL)
"""

from __future__ import annotations

import logging
import os
import re
import shlex
from typing import TYPE_CHECKING, Any

from .verdict import AccessLevel, PolicyVerdict

if TYPE_CHECKING:
    from ..config.models import CommandSecurityConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in safe commands (Claude Code style)
# ---------------------------------------------------------------------------

SAFE_COMMANDS: frozenset[str] = frozenset({
    # filesystem read
    "ls", "cat", "head", "tail", "less", "more", "wc", "file", "stat",
    "du", "df", "tree", "find", "locate", "readlink", "realpath",
    "basename", "dirname",
    # text processing
    "grep", "egrep", "fgrep", "rg", "awk", "sed",
    "sort", "uniq", "cut", "paste", "tr", "column", "jq", "yq",
    "diff", "cmp", "comm",
    # system info
    "uname", "hostname", "whoami", "id", "groups", "uptime", "free",
    "top", "htop", "ps", "lsof", "which", "whereis", "whatis",
    "man", "info", "type", "command",
    # shell builtins / utilities
    "echo", "printf", "date", "cal", "bc", "expr", "test", "true",
    "false", "pwd", "env", "printenv", "seq", "yes", "tput", "cd",
    # checksums
    "md5sum", "sha256sum", "sha1sum", "xxd", "od", "hexdump", "strings",
    # dev tools
    "python", "python3", "node", "ruby", "perl",
    "pip", "pip3", "npm", "pnpm", "yarn", "cargo", "go",
    "make", "cmake",
    # version control (subcommands checked separately)
    "git",
    # network
    "curl", "wget", "ping", "dig", "nslookup", "host",
})

GIT_SAFE_SUBCOMMANDS: frozenset[str] = frozenset({
    "status", "log", "diff", "show", "branch", "tag", "stash",
    "remote", "fetch", "ls-files", "ls-tree", "cat-file",
    "rev-parse", "describe", "shortlog", "blame", "reflog",
    "config", "version",
})

# ---------------------------------------------------------------------------
# Built-in dangerous patterns (Hermes Agent style)
# ---------------------------------------------------------------------------

DANGEROUS_PATTERNS: tuple[tuple[str, str], ...] = (
    # Destructive file operations
    (r"\brm\s+(-[^\s]*\s+)*/", "recursive delete"),
    (r"\brm\s+-[^\s]*r", "recursive delete"),
    (r"\brm\s+--recursive\b", "recursive delete"),
    (r"\bchmod\s+(-[^\s]*\s+)*(777|666|o\+[rwx]*w|a\+[rwx]*w)\b",
     "world-writable permissions"),
    (r"\bmkfs\b", "format filesystem"),
    (r"\bdd\s+.*if=", "disk copy"),
    (r">\s*/dev/sd", "write to block device"),

    # System file overwrites
    (r">\s*/etc/", "overwrite system config"),
    (r"\bsed\s+-[^\s]*i.*\s/etc/", "in-place edit system config"),
    (r"\bsystemctl\s+(-[^\s]+\s+)*(stop|restart|disable|mask)\b",
     "modify system service"),

    # SQL destructive
    (r"\bDROP\s+(TABLE|DATABASE)\b", "SQL DROP"),
    (r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", "SQL DELETE without WHERE"),
    (r"\bTRUNCATE\s+(TABLE)?\s*\w", "SQL TRUNCATE"),

    # Process killing
    (r"\bkill\s+-9\s+-1\b", "kill all processes"),
    (r"\bpkill\s+-9\b", "force kill processes"),

    # Shell injection / pipe-to-shell
    (r"\b(curl|wget)\b.*\|\s*(ba)?sh\b", "pipe remote content to shell"),
    (r":\(\)\s*\{", "fork bomb"),

    # Git destructive
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+push\b.*--force\b", "git force push"),
    (r"\bgit\s+push\b.*\s-f\b", "git force push"),
    (r"\bgit\s+clean\s+-[^\s]*f", "git clean with force"),
    (r"\bgit\s+branch\s+-D\b", "git branch force delete"),

    # Sensitive path writes
    (r">\s*~/\.ssh/", "write to SSH config"),
    (r">\s*~/\.env\b", "overwrite .env file"),
)

# Commands that always require approval regardless of safe list
_ALWAYS_REQUIRE: frozenset[str] = frozenset({"sudo"})

# Separators for splitting compound commands.
# A bare `;` is a shell separator; a `\;` is `find`'s -exec clause terminator
# and must NOT be treated as a compound split — the negative lookbehind keeps
# escaped semicolons intact so `_extract_find_inner_commands` can see them.
_COMPOUND_RE = re.compile(r"\s*(?:&&|\|\||(?<!\\);|\|)\s*")

# `find` action predicates that execute a nested command per match.
# `-exec` / `-execdir` run unattended; `-ok` / `-okdir` prompt interactively —
# all four still spawn the inner command, so the policy must inspect it.
_FIND_ACTION_PREDICATES: frozenset[str] = frozenset({
    "-exec", "-execdir", "-ok", "-okdir",
})

# Shells whose `-c "..."` payload is itself a full command line.
_SHELLS_WITH_DASH_C: frozenset[str] = frozenset({
    "sh", "bash", "zsh", "ksh", "dash", "ash",
})


# ---------------------------------------------------------------------------
# Command parsing helpers
# ---------------------------------------------------------------------------


def _extract_base_command(segment: str) -> str:
    """Extract the base command name from a single command segment.

    Handles:
    - Absolute paths: /usr/bin/ls → ls
    - env prefix: env HOME=/tmp ls → ls
    - Variable assignments: FOO=bar ls → ls
    """
    segment = segment.strip()
    if not segment:
        return ""

    tokens = segment.split()

    idx = 0
    # Skip leading variable assignments (FOO=bar) and env prefix
    while idx < len(tokens):
        token = tokens[idx]
        if token == "env" and idx + 1 < len(tokens):
            idx += 1
            continue
        if "=" in token and not token.startswith("-"):
            # VAR=value prefix
            idx += 1
            continue
        break

    if idx >= len(tokens):
        return ""

    cmd = tokens[idx]
    # Strip path: /usr/bin/ls → ls
    return os.path.basename(cmd)


def _split_compound(command: str) -> list[str]:
    """Split a compound command into individual segments."""
    return [s.strip() for s in _COMPOUND_RE.split(command) if s.strip()]


def _get_git_subcommand(segment: str) -> str | None:
    """Extract the git subcommand from a segment, or None if not a git command."""
    tokens = segment.split()
    for i, t in enumerate(tokens):
        if os.path.basename(t) == "git" and i + 1 < len(tokens):
            sub = tokens[i + 1]
            if not sub.startswith("-"):
                return sub
    return None


def _extract_find_inner_commands(segment: str) -> list[str]:
    """Extract inner commands from `find ... -exec CMD [ARGS] {\\; | +}` clauses.

    Returns the command strings that would actually execute per match. Handles
    all four action predicates (-exec, -execdir, -ok, -okdir), both terminators
    (\\; for per-match, + for batched), and multiple clauses on one line.

    Special case: when the inner command is a shell invoked with -c, the real
    payload lives inside the quoted string — that string is returned directly
    so it can be re-parsed.

    Returns an empty list if the segment isn't a `find` invocation with any
    action predicate, or if the tokens can't be parsed as a shell word list.
    """
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        # Unbalanced quotes etc. — let the outer evaluation decide.
        return []

    if not tokens:
        return []
    if os.path.basename(tokens[0]) != "find":
        return []

    inner: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] not in _FIND_ACTION_PREDICATES:
            i += 1
            continue

        # Collect tokens until the clause terminator `;` or `+`.
        start = i + 1
        end = start
        while end < len(tokens) and tokens[end] not in (";", "+"):
            end += 1

        clause = tokens[start:end]
        if clause:
            # `sh -c "<payload>"` / `bash -c "<payload>"` — the payload is
            # itself a command line and must be re-evaluated as such.
            if (
                len(clause) >= 3
                and os.path.basename(clause[0]) in _SHELLS_WITH_DASH_C
                and clause[1] == "-c"
            ):
                inner.append(clause[2])
            else:
                inner.append(shlex.join(clause))

        # Advance past the terminator (or end of tokens).
        i = end + 1

    return inner


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class CommandSecurityPolicy:
    """Evaluates shell commands for safety.

    Four-layer evaluation:
    1. Dangerous patterns (regex) — hard-block, cannot be overridden
    2. Durable approvals — previously approved commands auto-allow
    3. Safe command allowlist — auto-approve known-safe commands
    4. Unknown → require approval
    """

    def __init__(
        self,
        config: CommandSecurityConfig,
        approval_store: Any | None = None,
    ) -> None:
        extra_safe = config.extra_safe_commands or ()
        safe = SAFE_COMMANDS | frozenset(extra_safe)

        extra_patterns = tuple(
            (p.pattern, p.description) for p in config.extra_dangerous_patterns
        )
        patterns = DANGEROUS_PATTERNS + extra_patterns

        always_raw = config.always_require_approval or ()
        always_require = _ALWAYS_REQUIRE | frozenset(always_raw)
        safe = safe - always_require

        self._safe_commands = safe
        self._git_safe_subcommands = GIT_SAFE_SUBCOMMANDS
        self._always_require = always_require
        self._llm_config = config.llm_evaluation
        self._approval_store = approval_store

        # Pre-compile dangerous patterns
        self._dangerous: tuple[tuple[re.Pattern[str], str], ...] = tuple(
            (re.compile(pattern, re.IGNORECASE | re.DOTALL), desc)
            for pattern, desc in patterns
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def llm_enabled(self) -> bool:
        return self._llm_config.enabled

    @property
    def llm_config(self) -> dict[str, Any]:
        cfg = self._llm_config
        return {
            "enabled": cfg.enabled,
            "api_key": cfg.api_key,
            "model": cfg.model,
            "base_url": cfg.base_url,
        }

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, command: str) -> PolicyVerdict:
        """Evaluate a command synchronously (no LLM). Unknown → REQUIRE_APPROVAL."""
        if not command or not command.strip():
            return PolicyVerdict(
                level=AccessLevel.DENY, reason="empty command", policy="command",
            )

        # Check the full command against dangerous patterns first
        danger = self._check_dangerous(command)
        if danger is not None:
            return danger

        # Split compound commands and evaluate each segment
        segments = _split_compound(command)
        if not segments:
            return PolicyVerdict(
                level=AccessLevel.DENY, reason="empty command", policy="command",
            )

        for segment in segments:
            # Per-segment dangerous check (catches patterns within segments)
            danger = self._check_dangerous(segment)
            if danger is not None:
                return danger

            verdict = self._evaluate_segment(segment)
            if verdict.level != AccessLevel.ALLOW:
                return verdict

        return PolicyVerdict(
            level=AccessLevel.ALLOW, reason="all segments safe", policy="command",
        )

    async def evaluate_async(self, command: str, llm: Any = None) -> PolicyVerdict:
        """Evaluate with optional LLM for unknown commands.

        Falls back to sync evaluate() when LLM is disabled or unavailable.
        Dangerous patterns and safe allowlist are always checked first (sync).
        LLM is only consulted for REQUIRE_APPROVAL commands.
        """
        sync_verdict = self.evaluate(command)

        # If already decided (ALLOW or DENY), return immediately
        if sync_verdict.level != AccessLevel.REQUIRE_APPROVAL:
            return sync_verdict

        # REQUIRE_APPROVAL — try LLM if enabled and available
        if self.llm_enabled and llm is not None:
            return await self._llm_evaluate(command, llm)

        return sync_verdict

    async def _llm_evaluate(self, command: str, llm: Any) -> PolicyVerdict:
        """Call LLM to assess an unknown command's safety.

        Returns ALLOW on "SAFE", DENY on "UNSAFE", REQUIRE_APPROVAL on error.
        """
        prompt = (
            "You are a security reviewer for an AI assistant that runs shell commands. "
            "Assess whether this command is safe to execute without user confirmation.\n\n"
            f"Command: {command}\n\n"
            "Rules:\n"
            "- SAFE: read-only operations, development tools, package managers, "
            "build commands, non-destructive docker/kubectl commands\n"
            "- UNSAFE: anything that deletes data, modifies system config, "
            "overwrites files, kills processes, or has irreversible side effects\n"
            "- When uncertain, say UNSAFE\n\n"
            "Respond with exactly one word: SAFE or UNSAFE"
        )
        try:
            import asyncio

            response = await asyncio.wait_for(
                llm.complete(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=16,
                ),
                timeout=3,
            )
            answer = response.strip().upper()
            if "SAFE" in answer and "UNSAFE" not in answer:
                logger.info("LLM approved command: %s", command)
                return PolicyVerdict(
                    level=AccessLevel.ALLOW,
                    reason=f"LLM approved: {command}",
                    policy="command",
                )
            logger.info("LLM denied command: %s (response: %s)", command, answer)
            return PolicyVerdict(
                level=AccessLevel.DENY,
                reason=f"LLM denied: {command}",
                policy="command",
            )
        except Exception as e:
            logger.warning("LLM evaluation failed for '%s': %s — requiring approval", command, e)
            return PolicyVerdict(
                level=AccessLevel.REQUIRE_APPROVAL,
                reason=f"LLM error, requiring approval: {e}",
                policy="command",
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_dangerous(self, text: str) -> PolicyVerdict | None:
        """Check text against dangerous patterns. Returns DENY verdict if match."""
        for pattern, description in self._dangerous:
            if pattern.search(text):
                return PolicyVerdict(
                    level=AccessLevel.DENY,
                    reason=f"dangerous pattern: {description}",
                    policy="command",
                )
        return None

    def _evaluate_segment(self, segment: str) -> PolicyVerdict:
        """Evaluate a single command segment (no pipes/chains)."""
        base = _extract_base_command(segment)
        if not base:
            return PolicyVerdict(
                level=AccessLevel.REQUIRE_APPROVAL,
                reason="unknown command",
                policy="command",
            )

        # Always-require list (e.g. sudo)
        if base in self._always_require:
            return PolicyVerdict(
                level=AccessLevel.REQUIRE_APPROVAL,
                reason=f"always requires approval: {base}",
                policy="command",
            )

        # Git: check subcommand
        if base == "git":
            return self._evaluate_git(segment)

        # `find` is safe itself, but `-exec CMD \;` (and -execdir/-ok/-okdir)
        # runs CMD per match. Re-evaluate each inner command through the full
        # policy so dangerous inner commands can't smuggle past find's ALLOW.
        if base == "find":
            inner_verdict = self._evaluate_find_inner(segment)
            if inner_verdict is not None:
                return inner_verdict

        # Safe allowlist
        if base in self._safe_commands:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason=f"safe command: {base}",
                policy="command",
            )

        # Durable approvals — previously approved by user
        if self._approval_store is not None and self._approval_store.has(base):
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason=f"previously approved: {base}",
                policy="command",
            )

        # Unknown
        return PolicyVerdict(
            level=AccessLevel.REQUIRE_APPROVAL,
            reason=f"unknown command: {base}",
            policy="command",
        )

    def _evaluate_find_inner(self, segment: str) -> PolicyVerdict | None:
        """Evaluate any inner commands inside `find -exec ...` clauses.

        Returns the first non-ALLOW verdict, or ``None`` if there are no inner
        commands (so the caller falls through to the regular `find` allow).
        """
        inner_commands = _extract_find_inner_commands(segment)
        if not inner_commands:
            return None

        for inner in inner_commands:
            # Reuse the full public entry point so the inner command goes
            # through dangerous-pattern + compound + segment evaluation.
            verdict = self.evaluate(inner)
            if verdict.level != AccessLevel.ALLOW:
                return PolicyVerdict(
                    level=verdict.level,
                    reason=f"find -exec inner command: {verdict.reason}",
                    policy="command",
                )
        return None

    def _evaluate_git(self, segment: str) -> PolicyVerdict:
        """Evaluate a git command by its subcommand."""
        sub = _get_git_subcommand(segment)
        if sub is None:
            # Bare "git" or "git --version"
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="safe command: git",
                policy="command",
            )
        if sub in self._git_safe_subcommands:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason=f"safe git subcommand: {sub}",
                policy="command",
            )
        return PolicyVerdict(
            level=AccessLevel.REQUIRE_APPROVAL,
            reason=f"git subcommand requires approval: {sub}",
            policy="command",
        )
