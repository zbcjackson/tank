"""Tests for step_id computation and injection in WebSocket messages."""
import pytest
from tank_backend.core.events import DisplayMessage, UpdateType


def _compute_step_id(msg: DisplayMessage) -> str:
    """Replicate the step_id logic from router.py."""
    turn = msg.metadata.get("turn", 0)
    step_type = msg.update_type.name.lower()

    step_id = f"{msg.msg_id}_{step_type}_{turn}"

    if msg.update_type == UpdateType.TOOL:
        index = msg.metadata.get("index", 0)
        step_id += f"_{index}"

    return step_id


def test_step_id_for_text_message():
    msg = DisplayMessage(
        speaker="Brain", text="Hello world", is_user=False,
        msg_id="msg_abc123", update_type=UpdateType.TEXT,
        metadata={"turn": 1}
    )
    assert _compute_step_id(msg) == "msg_abc123_text_1"


def test_step_id_for_thinking_message():
    msg = DisplayMessage(
        speaker="Brain", text="Let me think...", is_user=False,
        msg_id="msg_abc123", update_type=UpdateType.THOUGHT,
        metadata={"turn": 1}
    )
    assert _compute_step_id(msg) == "msg_abc123_thought_1"


def test_step_id_for_tool():
    msg = DisplayMessage(
        speaker="Brain", text="", is_user=False,
        msg_id="msg_abc123", update_type=UpdateType.TOOL,
        metadata={"turn": 1, "index": 0, "name": "get_weather", "status": "calling"}
    )
    assert _compute_step_id(msg) == "msg_abc123_tool_1_0"


def test_tool_status_transitions_share_step_id():
    """All status transitions for the same tool share one step_id."""
    base = {"turn": 1, "index": 0, "name": "get_weather"}
    statuses = ["calling", "executing", "success"]
    step_ids = []
    for status in statuses:
        msg = DisplayMessage(
            speaker="Brain", text="", is_user=False,
            msg_id="msg_abc123", update_type=UpdateType.TOOL,
            metadata={**base, "status": status}
        )
        step_ids.append(_compute_step_id(msg))

    assert all(sid == "msg_abc123_tool_1_0" for sid in step_ids)


def test_step_id_for_multiple_turns():
    messages = [
        DisplayMessage(
            speaker="Brain", text="thinking...", is_user=False,
            msg_id="msg_abc123", update_type=UpdateType.THOUGHT,
            metadata={"turn": 1}
        ),
        DisplayMessage(
            speaker="Brain", text="", is_user=False,
            msg_id="msg_abc123", update_type=UpdateType.TOOL,
            metadata={"turn": 1, "index": 0, "status": "calling"}
        ),
        DisplayMessage(
            speaker="Brain", text="result", is_user=False,
            msg_id="msg_abc123", update_type=UpdateType.TEXT,
            metadata={"turn": 2}
        ),
    ]
    step_ids = [_compute_step_id(m) for m in messages]
    assert step_ids == [
        "msg_abc123_thought_1",
        "msg_abc123_tool_1_0",
        "msg_abc123_text_2",
    ]
    assert len(step_ids) == len(set(step_ids))


def test_step_id_for_multiple_tools_in_same_turn():
    messages = [
        DisplayMessage(
            speaker="Brain", text="", is_user=False,
            msg_id="msg_abc123", update_type=UpdateType.TOOL,
            metadata={"turn": 1, "index": 0, "name": "get_weather"}
        ),
        DisplayMessage(
            speaker="Brain", text="", is_user=False,
            msg_id="msg_abc123", update_type=UpdateType.TOOL,
            metadata={"turn": 1, "index": 1, "name": "get_time"}
        ),
    ]
    step_ids = [_compute_step_id(m) for m in messages]
    assert step_ids == ["msg_abc123_tool_1_0", "msg_abc123_tool_1_1"]
    assert len(step_ids) == len(set(step_ids))


def test_step_id_defaults_to_turn_0_when_missing():
    msg = DisplayMessage(
        speaker="Brain", text="Hello", is_user=False,
        msg_id="msg_abc123", update_type=UpdateType.TEXT,
        metadata={}
    )
    assert _compute_step_id(msg) == "msg_abc123_text_0"


def test_step_id_defaults_to_index_0_for_tools_when_missing():
    msg = DisplayMessage(
        speaker="Brain", text="", is_user=False,
        msg_id="msg_abc123", update_type=UpdateType.TOOL,
        metadata={"turn": 1}
    )
    assert _compute_step_id(msg) == "msg_abc123_tool_1_0"
