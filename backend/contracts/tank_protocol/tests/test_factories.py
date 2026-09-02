"""Factory output locks — representative frozen wire dicts from the
pre-extraction construction sites (protocol plan §8 P0-1: "构造工厂产出的帧
与现存手写构造逐字段 diff 为空")."""

from __future__ import annotations

from tank_protocol import (
    WebsocketAttachment,
    attachment,
    channel_notification,
    conversation_metadata_updated,
    signal,
    text,
    transcript,
    update,
)


def test_signal_factory_matches_handwritten():
    # from router.py SignalMessage forwarding
    assert (
        signal(
            "conversation_ready", session_id="s1", metadata={"foo": "bar"}
        ).model_dump()
        == {
            "type": "signal",
            "content": "conversation_ready",
            "speaker": None,
            "is_user": False,
            "is_final": False,
            "msg_id": None,
            "session_id": "s1",
            "metadata": {"foo": "bar"},
            "attachments": [],
        }
    )


def test_transcript_factory_matches_handwritten():
    assert (
        transcript(
            "你好",
            speaker="User",
            is_user=True,
            is_final=True,
            msg_id="u1",
            session_id="s1",
        ).model_dump_json()
        == '{"type":"transcript","content":"你好","speaker":"User","is_user":true,'
        '"is_final":true,"msg_id":"u1","session_id":"s1","metadata":{},'
        '"attachments":[]}'
    )


def test_text_factory_streams_partial():
    frame = text("Hel", speaker="Brain", msg_id="m1", session_id="s1")
    assert frame.is_final is False
    assert frame.type.value == "text"


def test_update_factory_puts_update_type_in_metadata():
    frame = update(
        "UpdateType.TOOL",
        msg_id="m1",
        session_id="s1",
        metadata={"step_id": "m1_tool_0", "status": "calling"},
    )
    assert frame.type.value == "update"
    assert frame.metadata["update_type"] == "UpdateType.TOOL"
    assert frame.speaker == "Brain"
    assert frame.metadata["step_id"] == "m1_tool_0"


def test_attachment_factory_is_always_final():
    frame = attachment(
        [WebsocketAttachment(url="/api/media/s1/x.jpg", caption="cap")],
        content="cap",
        msg_id="m1",
        session_id="s1",
    )
    assert frame.is_final is True
    assert frame.attachments[0].url == "/api/media/s1/x.jpg"


def test_channel_notification_factory_broadcasts_without_session():
    frame = channel_notification(
        metadata={"channel_slug": "jobs", "event_type": "job_delivery"}
    )
    assert frame.session_id is None
    assert frame.content == ""


def test_conversation_metadata_updated_factory_is_final():
    frame = conversation_metadata_updated(
        session_id="s1", metadata={"conversation_id": "c1", "title": "T"}
    )
    assert frame.is_final is True
    assert frame.content == ""


def test_factories_do_not_mutate_caller_metadata():
    meta = {"channel_slug": "jobs"}
    channel_notification(metadata=meta)
    assert meta == {"channel_slug": "jobs"}
