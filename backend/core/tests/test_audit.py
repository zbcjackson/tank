"""Tests for AuditLogger."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tank_backend.policy.audit import AuditLogger


@pytest.fixture
def audit_path(tmp_path: Path) -> str:
    return str(tmp_path / "audit.jsonl")


class TestAuditLogger:
    def test_disabled_is_noop(self, audit_path: str):
        logger = AuditLogger(log_path=audit_path, enabled=False)
        asyncio.get_event_loop().run_until_complete(
            logger.log_file_op("read", "/tmp/x", "allow", "default policy")
        )
        assert not Path(audit_path).exists()

    def test_log_file_op_writes_jsonl(self, audit_path: str):
        logger = AuditLogger(log_path=audit_path, enabled=True)
        asyncio.get_event_loop().run_until_complete(
            logger.log_file_op(
                "read", "/home/user/file.txt", "allow", "default policy", user="alice",
            )
        )

        lines = Path(audit_path).read_text().strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["category"] == "file"
        assert entry["operation"] == "read"
        assert entry["target"] == "/home/user/file.txt"
        assert entry["decision"] == "allow"
        assert entry["reason"] == "default policy"
        assert entry["user"] == "alice"
        assert "timestamp" in entry

    def test_log_network_op_writes_jsonl(self, audit_path: str):
        logger = AuditLogger(log_path=audit_path, enabled=True)
        asyncio.get_event_loop().run_until_complete(
            logger.log_network_op("pastebin.com", "require_approval", "Content sharing")
        )

        lines = Path(audit_path).read_text().strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["category"] == "network"
        assert entry["operation"] == "connect"
        assert entry["target"] == "pastebin.com"
        assert entry["decision"] == "require_approval"
        assert entry["reason"] == "Content sharing"

    def test_multiple_entries_append(self, audit_path: str):
        logger = AuditLogger(log_path=audit_path, enabled=True)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            logger.log_file_op("read", "/a", "allow", "r1")
        )
        loop.run_until_complete(
            logger.log_file_op("write", "/b", "deny", "r2")
        )
        loop.run_until_complete(
            logger.log_network_op("evil.onion", "deny", "r3")
        )

        lines = Path(audit_path).read_text().strip().split("\n")
        assert len(lines) == 3

        entries = [json.loads(line) for line in lines]
        assert entries[0]["operation"] == "read"
        assert entries[1]["operation"] == "write"
        assert entries[2]["operation"] == "connect"

    def test_log_file_op_no_user(self, audit_path: str):
        logger = AuditLogger(log_path=audit_path, enabled=True)
        asyncio.get_event_loop().run_until_complete(
            logger.log_file_op("delete", "/tmp/x", "deny", "secrets")
        )

        entry = json.loads(Path(audit_path).read_text().strip())
        assert entry["user"] == ""

    def test_from_dict_enabled(self):
        logger = AuditLogger.from_dict({"enabled": True, "log_path": "/tmp/test.jsonl"})
        assert logger._enabled is True
        assert str(logger._log_path) == "/tmp/test.jsonl"

    def test_from_dict_disabled(self):
        logger = AuditLogger.from_dict({"enabled": False})
        assert logger._enabled is False

    def test_from_dict_empty(self):
        logger = AuditLogger.from_dict({})
        assert logger._enabled is False

    def test_from_dict_none(self):
        logger = AuditLogger.from_dict(None)
        assert logger._enabled is False

    def test_creates_parent_dirs(self, tmp_path: Path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "audit.jsonl")
        logger = AuditLogger(log_path=deep_path, enabled=True)
        asyncio.get_event_loop().run_until_complete(
            logger.log_file_op("read", "/x", "allow", "test")
        )
        assert Path(deep_path).exists()
