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
        assert bus.subscribe.call_count == 2
        types = {call.args[0] for call in bus.subscribe.call_args_list}
        assert types == {"file_access_decision", "network_access_decision"}

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
