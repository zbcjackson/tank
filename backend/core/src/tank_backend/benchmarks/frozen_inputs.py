"""Verify caller-pinned file bytes and directory inventories without refreshing hashes."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrozenFile:
    path: Path
    sha256: str


@dataclass(frozen=True)
class FrozenInputs:
    files: tuple[FrozenFile, ...]
    trees: tuple[Path, ...] = ()

    def verify(self, required: Iterable[Path] = ()) -> None:
        paths = {item.path.resolve() for item in self.files}
        if not paths or len(paths) != len(self.files):
            raise ValueError("Frozen inputs must contain unique files")
        if not {path.resolve() for path in required} <= paths:
            raise ValueError("Frozen inputs do not cover required batch files")
        for item in self.files:
            if not re.fullmatch(r"[0-9a-f]{64}", item.sha256):
                raise ValueError("Frozen inputs contain an invalid SHA-256")
            try:
                actual = hashlib.sha256(item.path.read_bytes()).hexdigest()
            except OSError as exc:
                raise ValueError(f"Frozen inputs unavailable: {item.path}") from exc
            if actual != item.sha256:
                raise ValueError(f"Frozen inputs changed: {item.path}")
        for tree in self.trees:
            root = tree.resolve()
            if not tree.is_dir():
                raise ValueError(f"Frozen inputs directory unavailable: {tree}")
            actual_paths = {path.resolve() for path in tree.rglob("*") if path.is_file()}
            expected_paths = {path for path in paths if path.is_relative_to(root)}
            if actual_paths != expected_paths:
                raise ValueError(f"Frozen inputs directory inventory changed: {tree}")
