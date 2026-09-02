#!/usr/bin/env python3
"""Verify the protocol artifacts are in sync with the tank_protocol package.

Regenerates every committed artifact derived from the
``backend/contracts/tank_protocol`` package and fails on any diff:

- ``backend/contracts/tank_protocol/schema/tank_protocol.schema.json``
  (from ``python -m tank_protocol.schema``)
- ``device/test/test_native/test_ws_message/golden_frames.h`` (same generator)
- ``web/src/types/protocol.ts`` (from ``pnpm generate:protocol`` in web/)

Also checks that the package version in ``pyproject.toml`` matches the
``x-tank-version`` field of the regenerated schema (the version is the
protocol version consumed by the P1-1 handshake).

Exit codes: 0 = in sync, 1 = drift detected.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "backend" / "contracts" / "tank_protocol"
SCHEMA_PATH = PACKAGE_DIR / "schema" / "tank_protocol.schema.json"
GOLDEN_PATH = REPO_ROOT / "device" / "test" / "test_native" / "test_ws_message" / "golden_frames.h"
TS_PATH = REPO_ROOT / "web" / "src" / "types" / "protocol.ts"


def _run(cmd: list[str], **kwargs: object) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False,  # noqa: S603
        **kwargs,
    )
    if result.returncode != 0:
        print(f"command failed ({result.returncode}): {' '.join(cmd)}")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout


def _show_diff(committed: Path, regenerated: Path) -> None:
    # `git diff --no-index` exits 1 on differences — that is its job here,
    # not an error, so it must not go through _run().
    result = subprocess.run(  # noqa: S603
        ["git", "--no-pager", "diff", "--no-index", "--", str(committed), str(regenerated)],
        capture_output=True, text=True, check=False,
    )
    sys.stdout.write(result.stdout)


def _regenerate_python_artifacts(tmp: Path) -> None:
    _run(
        [
            "uv", "run", "--directory", str(PACKAGE_DIR),
            "python", "-m", "tank_protocol.schema",
            "--schema-out", str(tmp / "tank_protocol.schema.json"),
            "--golden-out", str(tmp / "golden_frames.h"),
        ]
    )


def _regenerate_ts(tmp: Path) -> None:
    # Run with cwd inside web/ — corepack resolves the project's pinned pnpm
    # from the working directory, and `--dir` bypasses that and breaks.
    _run(
        [
            "pnpm", "exec", "json2ts",
            "-i", str(SCHEMA_PATH),
            "-o", str(tmp / "protocol.ts"),
            "--banner-comment",
            (
                "Generated from backend/contracts/tank_protocol "
                "(tank_protocol package) — DO NOT EDIT. "
                "Regenerate: pnpm generate:protocol"
            ),
        ],
        cwd=str(REPO_ROOT / "web"),
    )


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)

        _regenerate_python_artifacts(tmp)
        _regenerate_ts(tmp)

        pairs = [
            (SCHEMA_PATH, tmp / "tank_protocol.schema.json"),
            (GOLDEN_PATH, tmp / "golden_frames.h"),
            (TS_PATH, tmp / "protocol.ts"),
        ]
        for committed, regenerated in pairs:
            if committed.read_bytes() != regenerated.read_bytes():
                failures.append(f"drift: {committed.relative_to(REPO_ROOT)}")
                _show_diff(committed, regenerated)

        # Version consistency: pyproject == schema x-tank-version (the
        # schema is generated from the package, which imports __version__).
        pyproject = tomllib.loads((PACKAGE_DIR / "pyproject.toml").read_text())
        pkg_version = pyproject["project"]["version"]
        schema_version = json.loads((tmp / "tank_protocol.schema.json").read_text())[
            "x-tank-version"
        ]
        if pkg_version != schema_version:
            failures.append(
                f"version mismatch: pyproject {pkg_version} != schema {schema_version}"
            )

    if failures:
        print("protocol sync check FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "regenerate with: cd backend/contracts/tank_protocol && "
            "uv run python -m tank_protocol.schema --schema-out schema/tank_protocol.schema.json "
            "--golden-out ../../../device/test/test_native/test_ws_message/golden_frames.h "
            "&& (cd ../../web && pnpm generate:protocol)"
        )
        return 1
    print("protocol sync check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
