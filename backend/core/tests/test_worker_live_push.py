"""Tests for live push-to-UI of background worker events via WebSocket."""

import json

from tank_backend.api.router import _worker_event_to_ws_msg
from tank_backend.api.schemas import MessageType


class TestWorkerEventToWsMsg:
    """Unit tests for _worker_event_to_ws_msg conversion."""

    def test_started_event_produces_calling_status(self):
        payload = {
            "event": "started",
            "task_id": "t_abc123",
            "agent_def": "research",
            "description": "Search for docs",
            "originating_conversation_id": "sess_1",
            "originating_channel": None,
            "parent_msg_id": "msg_42",
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")

        assert msg is not None
        assert msg.type == MessageType.UPDATE
        assert msg.metadata["status"] == "calling"
        assert msg.metadata["name"] == "agent"
        assert msg.metadata["update_type"] == "ACTIVITY.TOOL"
        assert msg.msg_id == "msg_42"
        assert msg.is_final is False
        assert msg.content == ""

    def test_completed_event_produces_success_with_output(self):
        payload = {
            "event": "completed",
            "task_id": "t_abc123",
            "agent_def": "research",
            "description": "Search for docs",
            "originating_conversation_id": "sess_1",
            "originating_channel": None,
            "parent_msg_id": "msg_42",
            "status": "completed",
            "output": "Found 3 relevant documents.",
            "error": None,
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")

        assert msg is not None
        assert msg.metadata["status"] == "success"
        assert msg.content == "Found 3 relevant documents."
        assert msg.is_final is True

    def test_failed_event_produces_error_with_message(self):
        payload = {
            "event": "failed",
            "task_id": "t_abc123",
            "agent_def": "research",
            "description": "Search for docs",
            "originating_conversation_id": "sess_1",
            "originating_channel": None,
            "parent_msg_id": None,
            "status": "failed",
            "output": "",
            "error": "LLM timeout after 30s",
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")

        assert msg is not None
        assert msg.metadata["status"] == "error"
        assert msg.content == "LLM timeout after 30s"
        assert msg.is_final is True
        # Falls back to worker_{task_id} when no parent_msg_id
        assert msg.msg_id == "worker_t_abc123"

    def test_cancelled_event_produces_error(self):
        payload = {
            "event": "cancelled",
            "task_id": "t_abc123",
            "agent_def": "research",
            "description": "Long task",
            "originating_conversation_id": "sess_1",
            "originating_channel": None,
            "parent_msg_id": None,
            "status": "cancelled",
            "output": "",
            "error": "Worker cancelled",
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")

        assert msg is not None
        assert msg.metadata["status"] == "error"
        assert msg.content == "Worker cancelled"

    def test_timeout_event_produces_error(self):
        payload = {
            "event": "timeout",
            "task_id": "t_abc123",
            "agent_def": "research",
            "description": "Slow task",
            "originating_conversation_id": "sess_1",
            "originating_channel": None,
            "parent_msg_id": None,
            "status": "timeout",
            "output": "partial",
            "error": "Worker timed out after 60.0s",
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")

        assert msg is not None
        assert msg.metadata["status"] == "error"
        assert msg.content == "Worker timed out after 60.0s"

    def test_unknown_event_returns_none(self):
        payload = {
            "event": "progress",
            "task_id": "t_abc123",
            "agent_def": "research",
            "description": "Task",
            "originating_conversation_id": "sess_1",
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")
        assert msg is None

    def test_missing_task_id_returns_none(self):
        payload = {"event": "started", "task_id": ""}
        msg = _worker_event_to_ws_msg(payload, "sess_1")
        assert msg is None

    def test_step_id_is_stable_across_events(self):
        """Same task_id produces same step_id so frontend upserts."""
        base = {
            "task_id": "t_xyz",
            "agent_def": "chat",
            "description": "Do stuff",
            "originating_conversation_id": "sess_1",
            "parent_msg_id": "msg_7",
        }
        started = _worker_event_to_ws_msg({**base, "event": "started"}, "sess_1")
        completed = _worker_event_to_ws_msg(
            {**base, "event": "completed", "status": "completed", "output": "done"},
            "sess_1",
        )
        assert started is not None
        assert completed is not None
        assert started.metadata["step_id"] == completed.metadata["step_id"]

    def test_arguments_contain_description_and_background_flag(self):
        payload = {
            "event": "started",
            "task_id": "t_abc",
            "agent_def": "research",
            "description": "Find papers on AI safety",
            "originating_conversation_id": "sess_1",
            "parent_msg_id": None,
        }
        msg = _worker_event_to_ws_msg(payload, "sess_1")
        assert msg is not None
        args = json.loads(msg.metadata["arguments"])
        assert args["description"] == "Find papers on AI safety"
        assert args["background"] is True
