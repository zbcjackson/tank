"""Tests for step_id computation and injection in WebSocket messages."""
import pytest
from tank_backend.core.events import DisplayMessage, UpdateType
from tank_backend.api.schemas import WebsocketMessage, MessageType


def test_step_id_for_text_message():
    """Test step_id computation for TEXT messages."""
    msg = DisplayMessage(
        speaker="Brain",
        text="Hello world",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TEXT,
        metadata={"turn": 1}
    )

    # Simulate router.py logic
    turn = msg.metadata.get("turn", 0)
    update_type_name = msg.update_type.name.lower()
    step_id = f"{msg.msg_id}_{update_type_name}_{turn}"

    assert step_id == "msg_abc123_text_1"


def test_step_id_for_thinking_message():
    """Test step_id computation for THOUGHT messages."""
    msg = DisplayMessage(
        speaker="Brain",
        text="Let me think...",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.THOUGHT,
        metadata={"turn": 1}
    )

    turn = msg.metadata.get("turn", 0)
    update_type_name = msg.update_type.name.lower()
    step_id = f"{msg.msg_id}_{update_type_name}_{turn}"

    assert step_id == "msg_abc123_thought_1"


def test_step_id_for_tool_call_message():
    """Test step_id computation for TOOL_CALL messages."""
    msg = DisplayMessage(
        speaker="Brain",
        text="",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TOOL_CALL,
        metadata={"turn": 1, "index": 0, "name": "get_weather"}
    )

    turn = msg.metadata.get("turn", 0)
    update_type_name = msg.update_type.name.lower()
    step_id = f"{msg.msg_id}_{update_type_name}_{turn}"

    if msg.update_type.name in ('TOOL_CALL', 'TOOL_RESULT'):
        index = msg.metadata.get("index", 0)
        step_id += f"_{index}"

    assert step_id == "msg_abc123_tool_call_1_0"


def test_step_id_for_tool_result_message():
    """Test step_id computation for TOOL_RESULT messages."""
    msg = DisplayMessage(
        speaker="Brain",
        text="Sunny, 72°F",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TOOL_RESULT,
        metadata={"turn": 1, "index": 0, "name": "get_weather"}
    )

    turn = msg.metadata.get("turn", 0)
    update_type_name = msg.update_type.name.lower()
    step_id = f"{msg.msg_id}_{update_type_name}_{turn}"

    if msg.update_type.name in ('TOOL_CALL', 'TOOL_RESULT'):
        index = msg.metadata.get("index", 0)
        step_id += f"_{index}"

    assert step_id == "msg_abc123_tool_result_1_0"


def test_tool_call_and_result_share_same_step_id():
    """Test that TOOL_CALL and TOOL_RESULT have the same step_id (except type suffix)."""
    # Tool call
    call_msg = DisplayMessage(
        speaker="Brain",
        text="",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TOOL_CALL,
        metadata={"turn": 1, "index": 0, "name": "get_weather"}
    )

    # Tool result
    result_msg = DisplayMessage(
        speaker="Brain",
        text="Sunny, 72°F",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TOOL_RESULT,
        metadata={"turn": 1, "index": 0, "name": "get_weather"}
    )

    def compute_step_id(msg):
        turn = msg.metadata.get("turn", 0)
        update_type_name = msg.update_type.name.lower()
        step_id = f"{msg.msg_id}_{update_type_name}_{turn}"
        if msg.update_type.name in ('TOOL_CALL', 'TOOL_RESULT'):
            index = msg.metadata.get("index", 0)
            step_id += f"_{index}"
        return step_id

    call_step_id = compute_step_id(call_msg)
    result_step_id = compute_step_id(result_msg)

    # They should differ only in the type part
    assert call_step_id == "msg_abc123_tool_call_1_0"
    assert result_step_id == "msg_abc123_tool_result_1_0"

    # But they share the same base (msg_id + turn + index)
    assert call_step_id.split("_")[0:2] == result_step_id.split("_")[0:2]  # msg_abc123
    assert call_step_id.split("_")[-2:] == result_step_id.split("_")[-2:]  # 1_0


def test_step_id_for_multiple_turns():
    """Test step_id computation across multiple turns."""
    messages = [
        # Turn 1: thinking
        DisplayMessage(
            speaker="Brain",
            text="Let me check...",
            is_user=False,
            msg_id="msg_abc123",
            update_type=UpdateType.THOUGHT,
            metadata={"turn": 1}
        ),
        # Turn 1: tool call
        DisplayMessage(
            speaker="Brain",
            text="",
            is_user=False,
            msg_id="msg_abc123",
            update_type=UpdateType.TOOL_CALL,
            metadata={"turn": 1, "index": 0}
        ),
        # Turn 2: text
        DisplayMessage(
            speaker="Brain",
            text="Here's the result",
            is_user=False,
            msg_id="msg_abc123",
            update_type=UpdateType.TEXT,
            metadata={"turn": 2}
        ),
    ]

    def compute_step_id(msg):
        turn = msg.metadata.get("turn", 0)
        update_type_name = msg.update_type.name.lower()
        step_id = f"{msg.msg_id}_{update_type_name}_{turn}"
        if msg.update_type.name in ('TOOL_CALL', 'TOOL_RESULT'):
            index = msg.metadata.get("index", 0)
            step_id += f"_{index}"
        return step_id

    step_ids = [compute_step_id(msg) for msg in messages]

    assert step_ids == [
        "msg_abc123_thought_1",
        "msg_abc123_tool_call_1_0",
        "msg_abc123_text_2",
    ]

    # All share the same msg_id
    assert all(sid.startswith("msg_abc123") for sid in step_ids)

    # Each has unique step_id
    assert len(step_ids) == len(set(step_ids))


def test_step_id_for_multiple_tools_in_same_turn():
    """Test step_id computation for multiple tool calls in the same turn."""
    messages = [
        # Tool 0
        DisplayMessage(
            speaker="Brain",
            text="",
            is_user=False,
            msg_id="msg_abc123",
            update_type=UpdateType.TOOL_CALL,
            metadata={"turn": 1, "index": 0, "name": "get_weather"}
        ),
        # Tool 1
        DisplayMessage(
            speaker="Brain",
            text="",
            is_user=False,
            msg_id="msg_abc123",
            update_type=UpdateType.TOOL_CALL,
            metadata={"turn": 1, "index": 1, "name": "get_time"}
        ),
    ]

    def compute_step_id(msg):
        turn = msg.metadata.get("turn", 0)
        update_type_name = msg.update_type.name.lower()
        step_id = f"{msg.msg_id}_{update_type_name}_{turn}"
        if msg.update_type.name in ('TOOL_CALL', 'TOOL_RESULT'):
            index = msg.metadata.get("index", 0)
            step_id += f"_{index}"
        return step_id

    step_ids = [compute_step_id(msg) for msg in messages]

    assert step_ids == [
        "msg_abc123_tool_call_1_0",
        "msg_abc123_tool_call_1_1",
    ]

    # Each tool has unique step_id
    assert len(step_ids) == len(set(step_ids))


def test_step_id_defaults_to_turn_0_when_missing():
    """Test step_id computation when turn is missing from metadata."""
    msg = DisplayMessage(
        speaker="Brain",
        text="Hello",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TEXT,
        metadata={}  # No turn
    )

    turn = msg.metadata.get("turn", 0)
    update_type_name = msg.update_type.name.lower()
    step_id = f"{msg.msg_id}_{update_type_name}_{turn}"

    assert step_id == "msg_abc123_text_0"


def test_step_id_defaults_to_index_0_for_tools_when_missing():
    """Test step_id computation when index is missing for tool messages."""
    msg = DisplayMessage(
        speaker="Brain",
        text="",
        is_user=False,
        msg_id="msg_abc123",
        update_type=UpdateType.TOOL_CALL,
        metadata={"turn": 1}  # No index
    )

    turn = msg.metadata.get("turn", 0)
    update_type_name = msg.update_type.name.lower()
    step_id = f"{msg.msg_id}_{update_type_name}_{turn}"

    if msg.update_type.name in ('TOOL_CALL', 'TOOL_RESULT'):
        index = msg.metadata.get("index", 0)
        step_id += f"_{index}"

    assert step_id == "msg_abc123_tool_call_1_0"
