"""Tests for AuditLogger — Bus subscriber pattern."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tank_backend.config.models import AuditConfig
from tank_backend.policy.audit import AuditLogger


@pytest.fixture
def audit_path(tmp_path: Path) -> str:
    return str(tmp_path / "audit.jsonl")


class TestAuditLogger:
    def test_disabled_is_noop(self, audit_path: str):
        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=False))
        bus = MagicMock()
        logger.subscribe(bus)
        # subscribe should not register handlers when disabled
        bus.subscribe.assert_not_called()

    def test_subscribe_registers_handlers(self, audit_path: str):
        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))
        bus = MagicMock()
        logger.subscribe(bus)
        assert bus.subscribe.call_count == 3
        types = {call.args[0] for call in bus.subscribe.call_args_list}
        assert types == {
            "file_access_decision",
            "network_access_decision",
            "connector_access_decision",
        }

    def test_on_file_decision_writes_jsonl(self, audit_path: str):
        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))
        msg = MagicMock()
        msg.payload = {
            "operation": "read",
            "path": "/home/user/file.txt",
            "level": "allow",
            "reason": "default policy",
        }

        logger._on_file_decision(msg)

        lines = Path(audit_path).read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["category"] == "file"
        assert entry["operation"] == "read"
        assert entry["target"] == "/home/user/file.txt"
        assert entry["decision"] == "allow"
        assert entry["reason"] == "default policy"
        assert "timestamp" in entry

    def test_on_network_decision_writes_jsonl(self, audit_path: str):
        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))
        msg = MagicMock()
        msg.payload = {
            "host": "pastebin.com",
            "level": "require_approval",
            "reason": "Content sharing",
        }

        logger._on_network_decision(msg)

        lines = Path(audit_path).read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["category"] == "network"
        assert entry["operation"] == "connect"
        assert entry["target"] == "pastebin.com"
        assert entry["decision"] == "require_approval"

    def test_multiple_entries_append(self, audit_path: str):
        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))

        msg1 = MagicMock()
        msg1.payload = {"operation": "read", "path": "/a", "level": "allow", "reason": "r1"}
        msg2 = MagicMock()
        msg2.payload = {"operation": "write", "path": "/b", "level": "deny", "reason": "r2"}
        msg3 = MagicMock()
        msg3.payload = {"host": "evil.onion", "level": "deny", "reason": "r3"}

        logger._on_file_decision(msg1)
        logger._on_file_decision(msg2)
        logger._on_network_decision(msg3)

        lines = Path(audit_path).read_text().strip().split("\n")
        assert len(lines) == 3

    def test_config_enabled(self):
        logger = AuditLogger(AuditConfig(enabled=True, log_path="/tmp/test.jsonl"))
        assert logger._enabled is True

    def test_config_disabled(self):
        logger = AuditLogger(AuditConfig(enabled=False))
        assert logger._enabled is False

    def test_config_defaults(self):
        logger = AuditLogger(AuditConfig())
        assert logger._enabled is False

    def test_creates_parent_dirs(self, tmp_path: Path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "audit.jsonl")
        logger = AuditLogger(AuditConfig(log_path=deep_path, enabled=True))
        msg = MagicMock()
        msg.payload = {"operation": "read", "path": "/x", "level": "allow", "reason": "test"}
        logger._on_file_decision(msg)
        assert Path(deep_path).exists()

    def test_on_connector_decision_writes_jsonl(self, audit_path: str):
        """Connector allowlist decisions share the JSONL schema with
        file/network entries — unified grep-ability for operators."""
        from tank_backend.policy.verdict import AccessLevel, PolicyVerdict

        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))
        verdict = PolicyVerdict(
            level=AccessLevel.DENY,
            reason="no matching rule; using default",
            policy="connector_access",
            context={
                "connector": "my-bot",
                "platform": "telegram",
                "external_id": "tg:user:99",
                "display_name": "Stranger",
            },
        )
        msg = MagicMock()
        msg.payload = {"verdict": verdict}

        logger._on_connector_decision(msg)

        lines = Path(audit_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["category"] == "connector"
        assert entry["operation"] == "inbound"
        assert entry["target"] == "tg:user:99"
        assert entry["decision"] == "deny"
        assert entry["connector"] == "my-bot"
        assert entry["platform"] == "telegram"
        assert entry["display_name"] == "Stranger"
        assert "timestamp" in entry

    def test_on_connector_decision_records_matched_pattern(
        self, audit_path: str,
    ):
        """Allow entries carry the glob pattern that matched — useful
        for debugging 'why did this user get through?' questions."""
        from tank_backend.policy.verdict import AccessLevel, PolicyVerdict

        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))
        verdict = PolicyVerdict(
            level=AccessLevel.ALLOW,
            reason="team",
            policy="connector_access",
            context={
                "connector": "my-bot",
                "platform": "telegram",
                "external_id": "tg:user:42",
                "display_name": "Alice",
                "matched_pattern": "tg:user:*",
            },
        )
        msg = MagicMock()
        msg.payload = {"verdict": verdict}
        logger._on_connector_decision(msg)

        entry = json.loads(Path(audit_path).read_text(encoding="utf-8").splitlines()[0])
        assert entry["matched_pattern"] == "tg:user:*"
        assert entry["decision"] == "allow"

    def test_on_connector_decision_tolerates_missing_verdict(
        self, audit_path: str,
    ):
        """Malformed payload must not crash the Bus loop — AuditLogger
        silently skips entries it can't parse."""
        logger = AuditLogger(AuditConfig(log_path=audit_path, enabled=True))
        msg = MagicMock()
        msg.payload = {}  # no "verdict" key

        logger._on_connector_decision(msg)

        # No file written, no exception.
        assert not Path(audit_path).exists()


# ---------------------------------------------------------------------------
# Phase 8 — size-based rotation
# ---------------------------------------------------------------------------


class TestAuditLogRotation:
    """The rotation path runs inline with every write_line. These tests
    cover the four states that matter: disabled (current behaviour),
    threshold respected, rotation happening, and recovery when the file
    disappears between stat and rename."""

    def test_max_bytes_zero_disables_rotation(self, audit_path: str):
        """Default config keeps pre-Phase-8 behaviour: writes append
        forever, no backup files are ever created. Operators running
        external logrotate shouldn't be surprised by mysterious
        ``.jsonl.1`` files."""
        logger = AuditLogger(AuditConfig(
            log_path=audit_path, enabled=True, max_bytes=0,
        ))
        msg = MagicMock()
        msg.payload = {
            "operation": "read", "path": "/x",
            "level": "allow", "reason": "t",
        }
        for _ in range(200):
            logger._on_file_decision(msg)

        # Live log grew freely; no backups were made.
        assert Path(audit_path).exists()
        assert not Path(audit_path + ".1").exists()

    def test_rotation_threshold_respected(self, audit_path: str):
        """With a generous cap, small writes don't trigger rotation even
        if many land — avoids per-entry renames burning disk I/O."""
        logger = AuditLogger(AuditConfig(
            log_path=audit_path, enabled=True,
            max_bytes=10 * 1024 * 1024,  # 10 MB
        ))
        msg = MagicMock()
        msg.payload = {
            "operation": "read", "path": "/x",
            "level": "allow", "reason": "t",
        }
        for _ in range(10):
            logger._on_file_decision(msg)

        assert Path(audit_path).exists()
        assert not Path(audit_path + ".1").exists()
        assert not Path(audit_path + ".2").exists()

    def test_rotation_creates_backup_on_overflow(self, audit_path: str):
        """When the live log crosses ``max_bytes``, the next write
        renames it to ``.jsonl.1`` and starts a fresh live file."""
        # Tiny cap so the very first write triggers rotation on the
        # second write's _maybe_rotate check.
        logger = AuditLogger(AuditConfig(
            log_path=audit_path, enabled=True, max_bytes=10,
        ))
        msg = MagicMock()
        msg.payload = {
            "operation": "read", "path": "/x",
            "level": "allow", "reason": "t",
        }
        logger._on_file_decision(msg)  # ~60 bytes → over the 10-byte cap
        # Next write notices the overflow and rotates before appending.
        logger._on_file_decision(msg)

        backup_path = Path(audit_path).with_suffix(".jsonl.1")
        assert backup_path.exists(), "backup was not created"
        # The live log exists again (fresh, with one entry).
        assert Path(audit_path).exists()
        assert len(Path(audit_path).read_text().splitlines()) == 1
        # Backup carries the first entry.
        assert len(backup_path.read_text().splitlines()) == 1

    def test_rotation_shifts_existing_backups_up(self, audit_path: str):
        """After ``backup_count`` rotations, ``.jsonl``, ``.jsonl.1``,
        …, ``.jsonl.N`` exist; nothing past N is kept."""
        logger = AuditLogger(AuditConfig(
            log_path=audit_path, enabled=True,
            max_bytes=10, backup_count=3,
        ))
        msg = MagicMock()
        msg.payload = {
            "operation": "read", "path": "/x",
            "level": "allow", "reason": "t",
        }
        # Each pair of writes triggers one rotation (the second write
        # sees the first's bytes and renames). Loop more than needed
        # to confirm the cap holds.
        for _ in range(10):
            logger._on_file_decision(msg)

        base = Path(audit_path)
        assert base.exists()
        assert base.with_suffix(".jsonl.1").exists()
        assert base.with_suffix(".jsonl.2").exists()
        assert base.with_suffix(".jsonl.3").exists()
        # backup_count=3 → nothing past .3 retained.
        assert not base.with_suffix(".jsonl.4").exists()
        assert not base.with_suffix(".jsonl.5").exists()

    def test_rotation_missing_file_is_a_noop(self, audit_path: str):
        """If the live file disappears between checks (external process
        rotated it out from under us), we just write a fresh one without
        raising."""
        logger = AuditLogger(AuditConfig(
            log_path=audit_path, enabled=True, max_bytes=10,
        ))
        # No file exists yet — rotation should noop and the write should
        # proceed.
        logger._maybe_rotate()

        msg = MagicMock()
        msg.payload = {
            "operation": "read", "path": "/x",
            "level": "allow", "reason": "t",
        }
        logger._on_file_decision(msg)
        assert Path(audit_path).exists()

    def test_backup_count_zero_drops_live_instead_of_renaming(
        self, audit_path: str,
    ):
        """With ``backup_count=0``, rotation truncates by unlinking —
        no backup file at all. Useful for deployments that forward
        entries to an external system and don't want local history."""
        logger = AuditLogger(AuditConfig(
            log_path=audit_path, enabled=True,
            max_bytes=10, backup_count=0,
        ))
        msg = MagicMock()
        msg.payload = {
            "operation": "read", "path": "/x",
            "level": "allow", "reason": "t",
        }
        logger._on_file_decision(msg)
        logger._on_file_decision(msg)

        # Live log has exactly one entry (the second write, after
        # rotation unlinked the first).
        assert len(Path(audit_path).read_text().splitlines()) == 1
        assert not Path(audit_path + ".1").exists()
