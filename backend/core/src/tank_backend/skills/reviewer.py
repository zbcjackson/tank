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
]

_ALLOWED_SCRIPT_EXTENSIONS = frozenset({".py", ".sh", ".bash"})

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
        risk_level = self._compute_risk(skill, has_scripts, dangerous_found)

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
    ) -> str:
        """Compute risk level based on review findings."""
        if dangerous_found:
            return "critical"

        declared_tools = set(skill.metadata.allowed_tools)

        if declared_tools & _HIGH_RISK_TOOLS:
            return "high"

        if has_scripts or (declared_tools & _NETWORK_TOOLS):
            return "medium"

        return "low"
