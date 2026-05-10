"""Text-only mode tests: verify ``wants_audio_input`` / ``wants_audio_output``
actually skip building the VAD/ASR/TTS/Playback processors, so connector
sessions don't waste cycles on audio nobody hears.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tank_backend.config.app_config import AppConfig
from tank_backend.config.context import AppContext
from tank_backend.core.assistant import Assistant

_MINIMAL_RAW = {
    "llm": {
        "default": {
            "api_key": "test-key",
            "model": "gpt-4",
            "base_url": "https://api.example.com/v1",
        },
    },
}


def _make_ctx(*, with_asr: bool, with_tts: bool) -> AppContext:
    """Build an AppContext with mocked audio engines that would otherwise
    load real models. The flags decide whether the engines are present at
    all — present engines + ``wants_audio_*=False`` is the interesting case
    (engines available globally, but this session opted out)."""
    from tank_backend.plugin.registry import ExtensionRegistry

    return AppContext(
        app_config=AppConfig.from_raw_dict(_MINIMAL_RAW),
        registry=ExtensionRegistry(),
        asr_engine=MagicMock(name="ASREngine") if with_asr else None,
        tts_engine=MagicMock(name="TTSEngine") if with_tts else None,
        vad_engine=MagicMock(name="VADEngine") if with_asr else None,
    )


class TestAssistantModalityFlags:
    def test_defaults_build_audio_processors_when_engines_available(self) -> None:
        """Backward-compat: old call-sites passing no flags get full audio."""
        ctx = _make_ctx(with_asr=True, with_tts=True)
        # Stub engine.create_stream so pipeline building doesn't touch real models.
        ctx.vad_engine.create_stream.return_value = MagicMock()  # type: ignore[union-attr]
        ctx.asr_engine.create_stream.return_value = MagicMock()  # type: ignore[union-attr]

        assistant = Assistant(app_context=ctx)

        assert assistant._vad_processor is not None  # noqa: SLF001
        assert assistant._tts_processor is not None  # noqa: SLF001
        assert assistant._playback_processor is not None  # noqa: SLF001
        assert assistant._has_asr is True  # noqa: SLF001
        assert assistant._has_tts is True  # noqa: SLF001

    def test_text_only_skips_all_audio_processors(self) -> None:
        """``wants_audio_input=False, wants_audio_output=False`` — the
        connector path — builds zero audio processors even though the
        engines exist in AppContext for other sessions."""
        ctx = _make_ctx(with_asr=True, with_tts=True)

        assistant = Assistant(
            app_context=ctx,
            wants_audio_input=False,
            wants_audio_output=False,
        )

        assert assistant._vad_processor is None  # noqa: SLF001
        assert assistant._tts_processor is None  # noqa: SLF001
        assert assistant._playback_processor is None  # noqa: SLF001
        assert assistant._has_asr is False  # noqa: SLF001
        assert assistant._has_tts is False  # noqa: SLF001
        # Engines in the shared context stay untouched — no streams created.
        ctx.vad_engine.create_stream.assert_not_called()  # type: ignore[union-attr]
        ctx.asr_engine.create_stream.assert_not_called()  # type: ignore[union-attr]

    def test_text_only_brain_disables_tts_emission(self) -> None:
        """Brain's ``tts_enabled`` gate is driven off the effective engine
        (overridden to None in text-only mode), so the Brain won't emit
        ``AudioOutputRequest`` at all."""
        ctx = _make_ctx(with_asr=True, with_tts=True)

        assistant = Assistant(
            app_context=ctx,
            wants_audio_input=False,
            wants_audio_output=False,
        )

        # The Brain carries the flag the pipeline builder passed in.
        assert assistant.brain._tts_enabled is False  # noqa: SLF001

    def test_audio_input_only(self) -> None:
        """Voice-in without voice-out (hypothetical Phase 4+ shape):
        VAD/ASR built, TTS/Playback skipped."""
        ctx = _make_ctx(with_asr=True, with_tts=True)
        ctx.vad_engine.create_stream.return_value = MagicMock()  # type: ignore[union-attr]
        ctx.asr_engine.create_stream.return_value = MagicMock()  # type: ignore[union-attr]

        assistant = Assistant(
            app_context=ctx,
            wants_audio_input=True,
            wants_audio_output=False,
        )

        assert assistant._vad_processor is not None  # noqa: SLF001
        assert assistant._tts_processor is None  # noqa: SLF001
        assert assistant._playback_processor is None  # noqa: SLF001

    def test_audio_output_only(self) -> None:
        """TTS/Playback built, VAD/ASR skipped (typed-only interactive WS
        client that wants to hear replies)."""
        ctx = _make_ctx(with_asr=True, with_tts=True)

        assistant = Assistant(
            app_context=ctx,
            wants_audio_input=False,
            wants_audio_output=True,
        )

        assert assistant._vad_processor is None  # noqa: SLF001
        assert assistant._tts_processor is not None  # noqa: SLF001
        assert assistant._playback_processor is not None  # noqa: SLF001
