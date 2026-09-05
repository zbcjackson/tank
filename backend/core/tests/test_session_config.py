"""P1-3: session hot-config and context-only injection.

Layers covered:

- ``VADStream`` session threshold — survives echo-guard's
  ``reset_threshold`` on playback end (the reason a plain ``set_threshold``
  was not enough).
- ``PromptAssembler.set_instructions`` — appended to the stable tier,
  replaced on re-send, cleared with ``None``, marks the prompt dirty.
- ``TTSProcessor.set_voice_override`` — per-request voice wins, override
  fills the gap, engine default when neither.
- ``Assistant.apply_session_config`` / ``inject_context`` — validate-all-
  then-apply (a rejected patch changes nothing) and role/content checks.
- Router dispatch — valid frames apply; rejected frames answer
  ``signal: error`` and leave the session untouched.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from tank_protocol import MessageType, WebsocketMessage

from tank_backend.api import deps
from tank_backend.api.manager import ConnectionManager
from tank_backend.api.router import (
    _handle_config_message,
    _handle_context_inject,
)
from tank_backend.api.server import app
from tank_backend.audio.input.types import SegmenterConfig
from tank_backend.audio.input.vad import VADStream
from tank_backend.channels.subscription import ChannelSubscriptionManager
from tank_backend.config import AppConfig
from tank_backend.config.context import AppContext
from tank_backend.core.assistant import Assistant
from tank_backend.core.events import AudioOutputRequest
from tank_backend.pipeline.processors.tts import TTSProcessor
from tank_backend.prompts.assembler import AssemblerConfig, PromptAssembler

# ---------------------------------------------------------------------------
# VADStream session threshold
# ---------------------------------------------------------------------------


class _FakeVADIterator:
    def __init__(self, model: Any, threshold: float, sampling_rate: int) -> None:
        self.threshold = threshold


@pytest.fixture
def stream(monkeypatch):
    monkeypatch.setattr(
        "tank_backend.audio.input.vad.VADIterator", _FakeVADIterator
    )
    engine = MagicMock()
    return VADStream(engine=engine, cfg=SegmenterConfig(speech_threshold=0.5))


def test_session_threshold_survives_echo_guard_reset(stream):
    assert stream._vad_iterator.threshold == pytest.approx(0.5)

    stream.set_session_threshold(0.8)
    assert stream._vad_iterator.threshold == pytest.approx(0.8)

    # Echo guard calls reset_threshold() on every playback end.
    stream.reset_threshold()
    assert stream._vad_iterator.threshold == pytest.approx(0.8)


def test_clearing_session_threshold_restores_default(stream):
    stream.set_session_threshold(0.8)
    stream.set_session_threshold(None)
    stream.reset_threshold()
    assert stream._vad_iterator.threshold == pytest.approx(0.5)


def test_reset_without_session_threshold_uses_default(stream):
    stream.reset_threshold()
    assert stream._vad_iterator.threshold == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# PromptAssembler instructions override
# ---------------------------------------------------------------------------


class _AssemblerHarness:
    def __init__(self, tmp_path: Any) -> None:
        defaults = tmp_path / "defaults"
        defaults.mkdir()
        (defaults / "base.md").write_text("BASE RULES", encoding="utf-8")
        user = tmp_path / "user_tank"
        user.mkdir()
        config = AssemblerConfig(
            user_dir=str(user), defaults_dir=str(defaults)
        )
        self.assembler = PromptAssembler(config=config)


def test_instructions_appended_to_stable_tier(tmp_path):
    h = _AssemblerHarness(tmp_path)
    h.assembler.set_instructions("Always answer in French")
    assert h.assembler.needs_rebuild()
    prompt = h.assembler.assemble()
    assert "SESSION INSTRUCTIONS" in prompt
    assert "Always answer in French" in prompt
    assert "BASE RULES" in prompt  # identity kept — append, not replace


def test_instructions_resend_replaces(tmp_path):
    h = _AssemblerHarness(tmp_path)
    h.assembler.set_instructions("Answer in French")
    h.assembler.assemble()
    h.assembler.set_instructions("Answer in German")
    prompt = h.assembler.assemble()
    assert "Answer in German" in prompt
    assert "Answer in French" not in prompt


def test_instructions_none_clears(tmp_path):
    h = _AssemblerHarness(tmp_path)
    h.assembler.set_instructions("Answer in French")
    h.assembler.set_instructions(None)
    assert "Answer in French" not in h.assembler.assemble()


# ---------------------------------------------------------------------------
# TTSProcessor voice override
# ---------------------------------------------------------------------------


def _recording_engine() -> tuple[MagicMock, list[str | None]]:
    """Mock TTSEngine recording the ``voice`` kwarg of each call."""
    engine = MagicMock()
    voices: list[str | None] = []

    def generate_stream(text: str, **kwargs: Any) -> Any:
        voices.append(kwargs.get("voice"))

        async def gen():
            yield SimpleNamespace(data=b"\x00\x00", sample_rate=24000, channels=1)

        return gen()

    engine.generate_stream.side_effect = generate_stream
    return engine, voices


async def _collect_tts_voice(
    engine: MagicMock, *, request_voice: str | None, override: str | None
) -> None:
    proc = TTSProcessor(tts_engine=engine)
    if override is not None:
        proc.set_voice_override(override)
    request = AudioOutputRequest(
        content="hello", language="en", voice=request_voice
    )
    async for _ in proc.process(request):
        pass


def test_tts_voice_override_applies_when_request_voice_none():
    engine, voices = _recording_engine()
    asyncio.run(
        _collect_tts_voice(
            engine, request_voice=None, override="zh-CN-YunxiNeural"
        )
    )
    assert voices == ["zh-CN-YunxiNeural"]


def test_tts_request_voice_beats_override():
    engine, voices = _recording_engine()
    asyncio.run(
        _collect_tts_voice(
            engine, request_voice="request-voice", override="override-voice"
        )
    )
    assert voices == ["request-voice"]


def test_tts_no_override_no_request_voice_keeps_default():
    engine, voices = _recording_engine()
    asyncio.run(_collect_tts_voice(engine, request_voice=None, override=None))
    assert voices == [None]


# ---------------------------------------------------------------------------
# Assistant.apply_session_config / inject_context
# ---------------------------------------------------------------------------


def _bare_assistant(**attrs: Any) -> Assistant:
    """Assistant without __init__ — unit target for the config methods."""
    assistant = Assistant.__new__(Assistant)
    assistant.brain = MagicMock()
    assistant._tts_processor = MagicMock()
    assistant._vad_processor = MagicMock()
    for name, value in attrs.items():
        setattr(assistant, name, value)
    return assistant


def test_apply_config_routes_all_keys():
    assistant = _bare_assistant()
    brain = cast(MagicMock, assistant.brain)
    tts = cast(MagicMock, assistant._tts_processor)
    vad = cast(MagicMock, assistant._vad_processor)
    assistant.apply_session_config(
        {
            "instructions": "Be terse",
            "voice": "zh-CN-YunxiNeural",
            "vad": {"speech_threshold": 0.7},
        }
    )
    brain.set_instructions.assert_called_once_with("Be terse")
    tts.set_voice_override.assert_called_once_with("zh-CN-YunxiNeural")
    vad.set_session_threshold.assert_called_once_with(0.7)


def test_apply_config_empty_is_noop():
    assistant = _bare_assistant()
    assistant.apply_session_config({})
    cast(MagicMock, assistant.brain).set_instructions.assert_not_called()


def test_apply_config_none_clears_instructions():
    assistant = _bare_assistant()
    assistant.apply_session_config({"instructions": None})
    cast(MagicMock, assistant.brain).set_instructions.assert_called_once_with(None)


@pytest.mark.parametrize(
    "patch",
    [
        "not-a-dict",
        {"unknown_key": 1},
        {"instructions": ""},
        {"instructions": 42},
        {"voice": ""},
        {"vad": "loud"},
        {"vad": {"unknown": 1}},
        {"vad": {"speech_threshold": "0.5"}},
        {"vad": {"speech_threshold": True}},
        {"vad": {"speech_threshold": 0.0}},
        {"vad": {"speech_threshold": 1.0}},
        {"vad": {"speech_threshold": -0.1}},
    ],
)
def test_apply_config_rejects_invalid(patch: Any):
    assistant = _bare_assistant()
    with pytest.raises(ValueError):
        assistant.apply_session_config(patch)


def test_apply_config_is_atomic():
    """Valid instructions + invalid vad → nothing applied."""
    assistant = _bare_assistant()
    with pytest.raises(ValueError):
        assistant.apply_session_config(
            {"instructions": "Be terse", "vad": {"speech_threshold": 9.0}}
        )
    cast(MagicMock, assistant.brain).set_instructions.assert_not_called()
    cast(
        MagicMock, assistant._vad_processor
    ).set_session_threshold.assert_not_called()


def test_apply_config_missing_processors_are_skipped():
    assistant = _bare_assistant(_tts_processor=None, _vad_processor=None)
    assistant.apply_session_config(
        {"voice": "some-voice", "vad": {"speech_threshold": 0.7}}
    )


def test_inject_context_forwards_to_brain():
    assistant = _bare_assistant()
    assistant.inject_context("RAG: the answer is 42.", role="system")
    cast(MagicMock, assistant.brain).inject_context.assert_called_once_with(
        "RAG: the answer is 42.", role="system"
    )


def test_inject_context_defaults_to_user_role():
    assistant = _bare_assistant()
    assistant.inject_context("a note")
    cast(MagicMock, assistant.brain).inject_context.assert_called_once_with(
        "a note", role="user"
    )


@pytest.mark.parametrize(
    "content, role",
    [("", "user"), ("   ", "user"), (None, "user"), ("note", "tool"), (42, "user")],
)
def test_inject_context_rejects_invalid(content: Any, role: Any):
    assistant = _bare_assistant()
    with pytest.raises(ValueError):
        assistant.inject_context(content, role=role)
    cast(MagicMock, assistant.brain).inject_context.assert_not_called()


# ---------------------------------------------------------------------------
# Router dispatch
# ---------------------------------------------------------------------------


def _config_frame(patch: Any) -> WebsocketMessage:
    metadata = {"config": patch} if patch is not None else {}
    return WebsocketMessage(type=MessageType.CONFIG, metadata=metadata)


def _inject_frame(content: Any = "note", role: Any = None) -> WebsocketMessage:
    metadata = {"role": role} if role else {}
    return WebsocketMessage(type=MessageType.CONTEXT_INJECT, content=content,
                            metadata=metadata)


async def test_router_config_applies_without_reply():
    assistant = _bare_assistant()
    send_fn = AsyncMock()
    await _handle_config_message(assistant, _config_frame({"voice": "v"}), "s1",
                                 send_fn)
    tts = cast(MagicMock, assistant._tts_processor)
    tts.set_voice_override.assert_called_once_with("v")
    send_fn.assert_not_awaited()


async def test_router_config_missing_patch_is_noop():
    assistant = _bare_assistant()
    send_fn = AsyncMock()
    await _handle_config_message(assistant, _config_frame(None), "s1", send_fn)
    cast(MagicMock, assistant.brain).set_instructions.assert_not_called()
    send_fn.assert_not_awaited()


async def test_router_config_rejection_sends_error_signal():
    assistant = _bare_assistant()
    send_fn = AsyncMock()
    await _handle_config_message(
        assistant, _config_frame({"nonsense": True}), "s1", send_fn
    )
    frame = send_fn.call_args[0][0]
    assert frame.type == MessageType.SIGNAL
    assert frame.content == "error"
    assert frame.metadata["error"].startswith("config rejected:")
    cast(MagicMock, assistant.brain).set_instructions.assert_not_called()


async def test_router_inject_forwards_role():
    assistant = _bare_assistant()
    send_fn = AsyncMock()
    await _handle_context_inject(
        assistant, _inject_frame("RAG result", role="system"), "s1", send_fn
    )
    cast(MagicMock, assistant.brain).inject_context.assert_called_once_with(
        "RAG result", role="system"
    )
    send_fn.assert_not_awaited()


async def test_router_inject_rejection_sends_error_signal():
    assistant = _bare_assistant()
    send_fn = AsyncMock()
    await _handle_context_inject(
        assistant, _inject_frame("note", role="robot"), "s1", send_fn
    )
    frame = send_fn.call_args[0][0]
    assert frame.type == MessageType.SIGNAL
    assert frame.content == "error"
    assert frame.metadata["error"].startswith("context_inject rejected:")


# ---------------------------------------------------------------------------
# /ws endpoint — config and context_inject over the real socket path
# ---------------------------------------------------------------------------


@pytest.fixture()
def harness(monkeypatch):
    """Same shape as test_ws_opus: real ConnectionManager + MagicMock
    assistant behind the real websocket_endpoint."""
    ctx = AppContext(app_config=AppConfig())
    mgr = ConnectionManager(app_context=ctx)
    assistant = MagicMock()
    assistant.capabilities = {"asr": True, "tts": True}
    assistant.pipeline_sample_rate = 16000
    assistant.capture_sample_rate = 16000
    assistant.capture_channels = 1
    assistant.brain.conversation_id = None
    callbacks: dict[str, Any] = {}
    assistant.set_playback_callback = lambda cb: callbacks.__setitem__("playback", cb)

    async def fake_get_or_create(session_id: str, **kwargs: Any):
        return assistant, True

    monkeypatch.setattr(mgr, "get_or_create_assistant", fake_get_or_create)
    sub_mgr = ChannelSubscriptionManager()
    prior = (
        deps._deps["ctx"],
        deps._mgr["v"],
        deps._sub_mgr["v"],
        deps._channel_audio["v"],
    )
    deps.init(ctx, mgr, sub_mgr, None)
    yield SimpleNamespace(mgr=mgr, assistant=assistant, sub_mgr=sub_mgr)
    deps._deps["ctx"], deps._mgr["v"], deps._sub_mgr["v"], deps._channel_audio["v"] = (
        prior
    )


def test_endpoint_config_applies(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        ws.send_text(
            json.dumps(
                {
                    "type": "config",
                    "content": "",
                    "metadata": {"config": {"voice": "some-voice"}},
                }
            )
        )
    harness.assistant.apply_session_config.assert_called_once_with({"voice": "some-voice"})


def test_endpoint_config_rejection_replies_error(harness):
    harness.assistant.apply_session_config.side_effect = ValueError("bad key")
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        ws.send_text(
            json.dumps(
                {"type": "config", "content": "", "metadata": {"config": {"x": 1}}}
            )
        )
        reply = json.loads(ws.receive_text())
    assert reply["type"] == "signal"
    assert reply["content"] == "error"
    assert "config rejected" in reply["metadata"]["error"]


def test_endpoint_context_inject_applies(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        ws.send_text(
            json.dumps(
                {
                    "type": "context_inject",
                    "content": "RAG: units are metric",
                    "metadata": {"role": "system"},
                }
            )
        )
    harness.assistant.inject_context.assert_called_once_with(
        "RAG: units are metric", role="system"
    )


def test_endpoint_context_inject_rejection_replies_error(harness):
    harness.assistant.inject_context.side_effect = ValueError("bad role")
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        ws.send_text(
            json.dumps(
                {
                    "type": "context_inject",
                    "content": "note",
                    "metadata": {},
                }
            )
        )
        reply = json.loads(ws.receive_text())
    assert reply["content"] == "error"
    assert "context_inject rejected" in reply["metadata"]["error"]
