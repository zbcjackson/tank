"""SecurityReviewer — static analysis and risk scoring for skills."""

from __future__ import annotations

import logging
import re

from .models import ReviewResult, SkillDefinition
from .parser import compute_directory_hash

logger = logging.getLogger(__name__)

# Patterns that indicate potentially dangerous code in skill scripts.
# Each tuple is (human-readable label, compiled regex).
_DANGEROUS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("dynamic code execution (eval)", re.compile(r"\beval\s*\(")),
    ("dynamic code execution (exec)", re.compile(r"\bexec\s*\(")),
    ("subprocess usage", re.compile(r"\bsubprocess\b")),
    ("os system call", re.compile(r"\bos\.system")),
    ("dynamic import", re.compile(r"\b__import__\s*\(")),
    ("code compilation", re.compile(r"\bcompile\s*\(")),
    ("raw socket usage", re.compile(r"\bsocket\b")),
    ("network library (requests)", re.compile(r"\bimport\s+requests\b")),
    ("network library (urllib)", re.compile(r"\bimport\s+urllib\b")),
    ("network library (httpx)", re.compile(r"\bimport\s+httpx\b")),
    ("destructive file op (rmtree)", re.compile(r"\bshutil\.rmtree\b")),
    ("destructive file op (remove)", re.compile(r"\bos\.(remove|unlink)\b")),
    ("base64 decoding", re.compile(r"\bbase64\.(b64decode|decodebytes)\b")),
    ("credential path access (~/.ssh)", re.compile(r"~/\.ssh")),
    ("credential path access (~/.aws)", re.compile(r"~/\.aws")),
    ("credential path access (~/.config)", re.compile(r"~/\.config")),
    ("shell download (curl)", re.compile(r"\bcurl\s+")),
    ("shell download (wget)", re.compile(r"\bwget\s+")),
    ("secret file access (.env)", re.compile(r"\b(open|read|cat)\b.*\.env\b")),
    ("secret file access (credentials)", re.compile(r"\bcredentials\.(json|yaml|yml|toml)\b")),
    ("secret file access (token)", re.compile(r"\btoken\.(json|yaml|yml|txt)\b")),
    ("raw IP address in URL", re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")),
]

# Patterns to detect in SKILL.md instructions (LLM prompt injection vectors).
_INSTRUCTION_RED_FLAGS: list[tuple[str, re.Pattern[str]]] = [
    ("references ~/.ssh", re.compile(r"~/\.ssh")),
    ("references ~/.aws", re.compile(r"~/\.aws")),
    ("references credential files", re.compile(
        r"\b(credentials|token|secret)\.(json|yaml|yml|toml|txt)\b"
    )),
    ("contains raw IP URL", re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")),
    ("contains base64 encoded data", re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")),
    ("instructs sending data externally", re.compile(
        r"\b(send|post|upload|exfiltrate)\b.*\b(to|http|url|endpoint)\b", re.IGNORECASE
    )),
]

_ALLOWED_SCRIPT_EXTENSIONS = frozenset({".py", ".sh", ".bash"})

# Maximum line length before flagging as potential obfuscation.
_OBFUSCATION_LINE_LENGTH = 500

_SAFE_TOOLS = frozenset({
    "get_weather", "get_time", "calculate", "list_skills",
})

_NETWORK_TOOLS = frozenset({
    "web_search", "web_fetch",
})

_HIGH_RISK_TOOLS = frozenset({
    "run_command", "persistent_shell", "manage_process",
    "file_read", "file_write", "file_delete", "file_list",
})


class SecurityReviewer:
    """Static security review pipeline for skills."""

    def review(self, skill: SkillDefinition) -> ReviewResult:
        """Run all review checks and return a ReviewResult."""
        findings: list[str] = []
        has_scripts = False

        # --- 1. Structure validation ---
        scripts_dir = skill.path / "scripts"
        if scripts_dir.exists():
            has_scripts = True
            for f in scripts_dir.rglob("*"):
                if f.is_file() and f.suffix not in _ALLOWED_SCRIPT_EXTENSIONS:
                    findings.append(
                        f"Unexpected file type in scripts/: {f.name} "
                        f"(allowed: {', '.join(sorted(_ALLOWED_SCRIPT_EXTENSIONS))})"
                    )

        # --- 2. Script static analysis ---
        dangerous_found = False
        if has_scripts:
            for f in scripts_dir.rglob("*"):
                if not f.is_file() or f.suffix not in _ALLOWED_SCRIPT_EXTENSIONS:
                    continue
                content = f.read_text(encoding="utf-8", errors="replace")
                for label, pattern in _DANGEROUS_PATTERNS:
                    if pattern.search(content):
                        findings.append(f"Dangerous pattern in {f.name}: {label}")
                        dangerous_found = True
                # Check for obfuscated code (very long lines)
                for i, line in enumerate(content.splitlines(), 1):
                    if len(line) > _OBFUSCATION_LINE_LENGTH:
                        findings.append(
                            f"Possible obfuscation in {f.name} line {i}: "
                            f"line length {len(line)} chars"
                        )
                        dangerous_found = True
                        break  # One finding per file is enough

        # --- 2b. Instruction content analysis ---
        instructions_suspicious = False
        for label, pattern in _INSTRUCTION_RED_FLAGS:
            if pattern.search(skill.instructions):
                findings.append(f"Suspicious instruction content: {label}")
                instructions_suspicious = True

        # --- 3. Tool scope check ---
        declared_tools = set(skill.metadata.allowed_tools)
        instructions_lower = skill.instructions.lower()
        all_known_tools = _SAFE_TOOLS | _NETWORK_TOOLS | _HIGH_RISK_TOOLS
        for tool_name in all_known_tools:
            if tool_name in instructions_lower and tool_name not in declared_tools:
                findings.append(
                    f"Instructions reference tool '{tool_name}' "
                    f"not declared in allowed-tools field"
                )

        # --- 4. Risk scoring ---
        risk_level = self._compute_risk(
            skill, has_scripts, dangerous_found, instructions_suspicious,
        )

        content_hash = compute_directory_hash(skill.path)
        passed = risk_level != "critical"

        return ReviewResult(
            passed=passed,
            risk_level=risk_level,
            findings=tuple(findings),
            content_hash=content_hash,
        )

    def _compute_risk(
        self,
        skill: SkillDefinition,
        has_scripts: bool,
        dangerous_found: bool,
        instructions_suspicious: bool,
    ) -> str:
        """Compute risk level based on review findings."""
        if dangerous_found:
            return "critical"

        declared_tools = set(skill.metadata.allowed_tools)

        if declared_tools & _HIGH_RISK_TOOLS:
            return "high"

        if has_scripts or (declared_tools & _NETWORK_TOOLS):
            return "medium"

        if instructions_suspicious:
            return "medium"

        return "low"
