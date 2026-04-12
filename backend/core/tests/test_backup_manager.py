"""Tests for BackupManager — snapshot, cleanup, from_dict."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tank_backend.policy.backup import BackupManager


@pytest.fixture
def tmp_backup_dir(tmp_path: Path) -> Path:
    return tmp_path / "backups"


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    f = tmp_path / "original.txt"
    f.write_text("hello world")
    return f


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_creates_backup(tmp_backup_dir: Path, sample_file: Path):
    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30)
    result = await mgr.snapshot(str(sample_file))

    assert result is not None
    backup = Path(result)
    assert backup.exists()
    assert backup.read_text() == "hello world"


@pytest.mark.asyncio
async def test_snapshot_returns_none_for_nonexistent(tmp_backup_dir: Path):
    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30)
    result = await mgr.snapshot("/nonexistent/file.txt")
    assert result is None


@pytest.mark.asyncio
async def test_snapshot_returns_none_when_disabled(tmp_backup_dir: Path, sample_file: Path):
    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30, enabled=False)
    result = await mgr.snapshot(str(sample_file))
    assert result is None


@pytest.mark.asyncio
async def test_snapshot_preserves_content(tmp_backup_dir: Path, tmp_path: Path):
    f = tmp_path / "data.bin"
    f.write_text("line1\nline2\nline3")
    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30)

    result = await mgr.snapshot(str(f))
    assert result is not None
    assert Path(result).read_text() == "line1\nline2\nline3"


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def test_cleanup_removes_old_backups(tmp_backup_dir: Path):
    # Create an old backup dir (40 days ago)
    old_time = datetime.now() - timedelta(days=40)
    old_dir = tmp_backup_dir / old_time.strftime("%Y-%m-%dT%H-%M-%S")
    old_dir.mkdir(parents=True)
    (old_dir / "file.txt").write_text("old")

    # Create a recent backup dir
    recent_dir = tmp_backup_dir / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    recent_dir.mkdir(parents=True)
    (recent_dir / "file.txt").write_text("recent")

    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30)
    mgr._cleanup_old_backups()

    assert not old_dir.exists()
    assert recent_dir.exists()


def test_cleanup_keeps_recent_backups(tmp_backup_dir: Path):
    recent_dir = tmp_backup_dir / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    recent_dir.mkdir(parents=True)
    (recent_dir / "file.txt").write_text("keep me")

    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30)
    mgr._cleanup_old_backups()

    assert recent_dir.exists()


def test_cleanup_ignores_non_timestamp_dirs(tmp_backup_dir: Path):
    weird_dir = tmp_backup_dir / "not-a-timestamp"
    weird_dir.mkdir(parents=True)

    mgr = BackupManager(backup_dir=str(tmp_backup_dir), max_age_days=30)
    mgr._cleanup_old_backups()  # Should not raise

    assert weird_dir.exists()


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------

def test_from_dict_empty():
    mgr = BackupManager.from_dict({})
    assert mgr._enabled is True
    assert mgr._max_age_days == 30


def test_from_dict_full():
    mgr = BackupManager.from_dict({
        "enabled": False,
        "path": "/custom/backups",
        "max_age_days": 7,
    })
    assert mgr._enabled is False
    assert mgr._max_age_days == 7
    assert str(mgr._backup_dir) == "/custom/backups"


def test_from_dict_defaults():
    mgr = BackupManager.from_dict({"enabled": True})
    assert mgr._max_age_days == 30
