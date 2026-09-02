#!/usr/bin/env python3
"""Consistency checks for docs/ — run like a test suite.

    python3 scripts/check_docs.py

Exit 0 = all checks pass, 1 = failures (printed as file:line messages).
Stdlib only; runnable from any cwd.

Enforces the rules documented in CLAUDE.md ("Documentation (docs/)"):

1. Naming      — files and directories under docs/ are lowercase
                 kebab-case. docs/superpowers/ is plugin-managed and
                 exempt; docs/README.md is allowed as-is.
2. Plan status — every doc in plans/active|done opens with a status
                 line ('> 状态：…' or '> **Status:** …'). done/ plans
                 must claim completion; active/ plans must not.
3. References  — every 'docs/….md' path mentioned anywhere in the repo
                 resolves to an existing file; every relative .md link
                 inside docs/ resolves (#fragment is stripped).
4. Index       — docs/README.md links every doc under docs/ and links
                 no missing ones.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

EXCLUDED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".pio", "managed_components",  # vendored third-party code (device/)
}
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".ts", ".tsx", ".rs", ".json", ".toml", ".sh", ".txt"}

KEBAB_DIR = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KEBAB_FILE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
STATUS_LINE = re.compile(r"^>\s*(状态[：:]|\*\*Status:\*\*)")
DONE_MARKER = re.compile(r"已完成|\bcomplete\b|shipped", re.IGNORECASE)
DOC_REF = re.compile(r"docs/[A-Za-z0-9_./-]+\.md")
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
URL_SCHEMES = ("http://", "https://", "mailto:")

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def iter_text_files(root: Path, skip_superpowers: bool = False):
    """Yield text files under root, skipping excluded dirs (and docs/superpowers/)."""
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        rel = p.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if skip_superpowers and rel.parts[0] == "superpowers":
            continue
        yield p


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def check_naming() -> None:
    for p in sorted(DOCS.rglob("*")):
        rel = p.relative_to(DOCS)
        if rel.parts[0] == "superpowers":
            continue
        if p.is_dir():
            if not KEBAB_DIR.match(p.name):
                fail(f"naming: docs/{rel}/ is not lowercase kebab-case")
        elif p.suffix == ".md" and p.name != "README.md":
            if not KEBAB_FILE.match(p.name):
                fail(f"naming: docs/{rel} is not lowercase kebab-case")


def check_plan_status() -> None:
    for sub in ("active", "done"):
        for p in sorted((DOCS / "plans" / sub).glob("*.md")):
            head = read(p)[:2000]
            found = [line for line in head.splitlines() if STATUS_LINE.match(line)]
            if not found:
                fail(f"plan-status: docs/plans/{sub}/{p.name} has no status line "
                     f"('> 状态：…' or '> **Status:** …') near the top")
                continue
            status = found[0]
            if sub == "done" and not DONE_MARKER.search(status):
                fail(f"plan-status: docs/plans/done/{p.name} sits in done/ but its "
                     f"status line does not claim completion: {status.strip()}")
            if sub == "active" and DONE_MARKER.search(status):
                fail(f"plan-status: docs/plans/active/{p.name} claims completion "
                     f"but sits in active/ — move it to plans/done/: {status.strip()}")


def check_references() -> None:
    # 'docs/….md' mentioned anywhere in the repo must exist. A match
    # preceded by '/' or ':' is a URL path segment (e.g. mozilla docs), not
    # a repo-relative reference.
    for p in iter_text_files(ROOT):
        rel = p.relative_to(ROOT)
        if rel.parts[:2] == ("docs", "superpowers"):
            continue
        text = read(p)
        for m in DOC_REF.finditer(text):
            if m.start() > 0 and text[m.start() - 1] in "/:":
                continue
            if not (ROOT / m.group(0)).is_file():
                fail(f"{rel}:{line_of(text, m.start())}: reference '{m.group(0)}' does not exist")

    # Relative .md links inside docs/ must resolve.
    for p in iter_text_files(DOCS, skip_superpowers=True):
        rel = p.relative_to(ROOT)
        text = read(p)
        for m in MD_LINK.finditer(text):
            target = m.group(1)
            if target.startswith(URL_SCHEMES) or target.startswith("#"):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part.endswith(".md"):
                continue
            if not (p.parent / path_part).resolve().is_file():
                fail(f"{rel}:{line_of(text, m.start())}: link '({target})' does not resolve")


def check_index() -> None:
    readme = DOCS / "README.md"
    text = read(readme)
    linked: set[Path] = set()
    for m in MD_LINK.finditer(text):
        target = m.group(1)
        if target.startswith(URL_SCHEMES):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part.endswith(".md"):
            continue
        linked.add((readme.parent / path_part).resolve())

    actual = {
        p.resolve()
        for p in DOCS.rglob("*.md")
        if p.relative_to(DOCS).parts[0] != "superpowers" and p.name != "README.md"
    }
    for f in sorted(actual - linked):
        fail(f"index: docs/{f.relative_to(DOCS)} is not linked from docs/README.md")
    for f in sorted(linked - actual):
        if DOCS not in f.parents or f.is_file():
            continue  # links outside docs/ (e.g. ../CLAUDE.md) or to real files
        fail(f"index: docs/README.md links docs/{f.relative_to(DOCS)} which does not exist")


def main() -> int:
    if not DOCS.is_dir():
        print(f"docs check: {DOCS} not found — nothing to check")
        return 1
    check_naming()
    check_plan_status()
    check_references()
    check_index()

    if failures:
        print(f"docs check: {len(failures)} failure(s)\n")
        for f in failures:
            print(f"  FAIL {f}")
        return 1
    n_docs = sum(1 for _ in DOCS.rglob("*.md"))
    print(f"docs check: OK ({n_docs} files under docs/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
