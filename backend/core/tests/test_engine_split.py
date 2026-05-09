"""Tests for the ASR/VAD engine+stream split.

Validates the Phase 1 refactor: a process-global engine owns the model,
per-session streams are cheap wrappers, and the ``transcribe_once()``
convenience works end-to-end with mocked sherpa.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from tank_contracts import ASREngine, ASRStream


class _FakeASREngine(ASREngine):
    """Minimal ASREngine for testing stream creation and transcribe_once."""

    def __init__(self, final_text: str = "hello") -> None:
        self._final_text = final_text
        self.streams_created = 0
        self.closed = False

    def create_stream(self) -> ASRStream:
        self.streams_created += 1
        return _FakeASRStream(self._final_text)

    def close(self) -> None:
        self.closed = True


class _FakeASRStream(ASRStream):
    """Records calls; returns configured transcript on stop."""

    def __init__(self, final_text: str) -> None:
        self._final_text = final_text
        self.chunks_seen: list[np.ndarray] = []
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def process_pcm(self, pcm: np.ndarray) -> str:
        self.chunks_seen.append(pcm)
        return ""

    def stop(self) -> str:
        self.stopped = True
        return self._final_text

    def close(self) -> None:
        self.closed = True


class TestTranscribeOnce:
    """``ASREngine.transcribe_once`` runs the full lifecycle and returns
    the final transcript."""

    async def test_returns_final_transcript(self) -> None:
        engine = _FakeASREngine(final_text="hello world")
        pcm = np.zeros(16000, dtype=np.float32)

        result = await engine.transcribe_once(pcm, sample_rate=16000)

        assert result == "hello world"

    async def test_creates_and_disposes_stream(self) -> None:
        engine = _FakeASREngine()
        pcm = np.zeros(16000, dtype=np.float32)

        await engine.transcribe_once(pcm)

        # A fresh stream was created for this one-shot call.
        assert engine.streams_created == 1

    async def test_calls_full_lifecycle(self) -> None:
        """start → process_pcm → stop → close, in order."""
        captured_stream: dict = {}

        class _CapturingEngine(_FakeASREngine):
            def create_stream(self) -> ASRStream:
                stream = super().create_stream()
                captured_stream["stream"] = stream
                return stream

        engine = _CapturingEngine()
        pcm = np.zeros(8000, dtype=np.float32)

        await engine.transcribe_once(pcm)

        stream = captured_stream["stream"]
        assert stream.started
        assert len(stream.chunks_seen) == 1
        assert stream.stopped
        assert stream.closed

    async def test_closes_stream_on_exception(self) -> None:
        """If process_pcm raises, the stream is still closed."""

        class _RaisingStream(_FakeASRStream):
            def process_pcm(self, pcm: np.ndarray) -> str:
                raise RuntimeError("synthetic failure")

        captured: dict = {}

        class _RaisingEngine(_FakeASREngine):
            def create_stream(self) -> ASRStream:
                stream = _RaisingStream(self._final_text)
                captured["stream"] = stream
                return stream

        engine = _RaisingEngine()

        with pytest.raises(RuntimeError, match="synthetic failure"):
            await engine.transcribe_once(np.zeros(1000, dtype=np.float32))

        assert captured["stream"].closed, "stream.close() must run even on exception"


class TestEngineStreamIsolation:
    """Multiple streams from one engine don't share per-session state."""

    async def test_streams_are_independent_instances(self) -> None:
        engine = _FakeASREngine()

        stream_a = engine.create_stream()
        stream_b = engine.create_stream()

        assert stream_a is not stream_b

    async def test_streams_accumulate_independent_state(self) -> None:
        engine = _FakeASREngine()

        stream_a = engine.create_stream()
        stream_b = engine.create_stream()

        stream_a.start()
        stream_b.start()

        stream_a.process_pcm(np.zeros(100, dtype=np.float32))
        stream_b.process_pcm(np.ones(200, dtype=np.float32))

        assert len(stream_a.chunks_seen) == 1  # type: ignore[attr-defined]
        assert len(stream_b.chunks_seen) == 1  # type: ignore[attr-defined]
        assert stream_a.chunks_seen[0].shape == (100,)  # type: ignore[attr-defined]
        assert stream_b.chunks_seen[0].shape == (200,)  # type: ignore[attr-defined]


class TestSherpaEngineSplit:
    """The sherpa plugin loads the ONNX model once and shares it across
    many cheap streams.

    Uses mocked sherpa symbols to avoid loading real ONNX files.
    """

    def _mock_sherpa_symbols(self):
        """Return a tuple matching _load_sherpa()'s return shape, with
        everything as MagicMocks."""
        return tuple(MagicMock() for _ in range(9))

    def test_engine_loads_model_once(self, tmp_path) -> None:
        """Creating many streams does NOT reload the model."""
        # Create the model dir + expected files so the FileNotFoundError gate
        # in SherpaASREngine.__init__ passes.
        model_dir = tmp_path / "sherpa-model"
        model_dir.mkdir()
        for name in (
            "encoder-epoch-99-avg-1.onnx",
            "decoder-epoch-99-avg-1.onnx",
            "joiner-epoch-99-avg-1.onnx",
            "tokens.txt",
        ):
            (model_dir / name).touch()

        with patch(
            "asr_sherpa.engine._load_sherpa",
            return_value=self._mock_sherpa_symbols(),
        ) as load_sherpa:
            from asr_sherpa.engine import SherpaASREngine

            engine = SherpaASREngine(model_dir=str(model_dir))

            # Initial construction loaded sherpa once.
            assert load_sherpa.call_count == 1

            # Creating 20 streams must not trigger any additional loads.
            for _ in range(20):
                engine.create_stream()

            assert load_sherpa.call_count == 1

    def test_streams_share_engine_recognizer(self, tmp_path) -> None:
        """All streams from one engine reference the same recognizer, and
        each stream comes from a separate ``recognizer.create_stream()`` call
        (so they carry independent per-utterance decoder state).
        """
        model_dir = tmp_path / "sherpa-model"
        model_dir.mkdir()
        for name in (
            "encoder-epoch-99-avg-1.onnx",
            "decoder-epoch-99-avg-1.onnx",
            "joiner-epoch-99-avg-1.onnx",
            "tokens.txt",
        ):
            (model_dir / name).touch()

        with patch(
            "asr_sherpa.engine._load_sherpa",
            return_value=self._mock_sherpa_symbols(),
        ):
            from asr_sherpa.engine import SherpaASREngine

            engine = SherpaASREngine(model_dir=str(model_dir))
            recognizer = engine._recognizer  # type: ignore[attr-defined]
            # Clear any construction-time calls before counting.
            recognizer.create_stream.reset_mock()

            stream_a = engine.create_stream()
            stream_b = engine.create_stream()

            # Both streams reference the engine's single recognizer.
            assert stream_a._recognizer is engine._recognizer  # type: ignore[attr-defined]
            assert stream_b._recognizer is engine._recognizer  # type: ignore[attr-defined]
            # recognizer.create_stream() was called once per stream.
            assert recognizer.create_stream.call_count == 2


class TestVADEngineSplit:
    """VADEngine loads Silero once; streams share the model."""

    def test_engine_loads_silero_once(self) -> None:
        """``VADEngine()`` calls ``load_silero_vad`` exactly once, and
        creating N streams does not load additional models."""
        with patch(
            "tank_backend.audio.input.vad.load_silero_vad",
        ) as load_silero:
            load_silero.return_value = MagicMock(name="SileroModel")

            from tank_backend.audio.input.vad import VADEngine

            engine = VADEngine()
            assert load_silero.call_count == 1

            # Create many streams; model should not reload.
            for _ in range(10):
                engine.create_stream()

            assert load_silero.call_count == 1

    def test_streams_share_engine_model(self) -> None:
        """All streams from one engine reference the same Silero model."""
        with patch(
            "tank_backend.audio.input.vad.load_silero_vad",
        ) as load_silero:
            shared_model = MagicMock(name="SileroModel")
            load_silero.return_value = shared_model

            from tank_backend.audio.input.vad import VADEngine

            engine = VADEngine()
            stream_a = engine.create_stream()
            stream_b = engine.create_stream()

            assert stream_a._engine._model is shared_model  # type: ignore[attr-defined]
            assert stream_b._engine._model is shared_model  # type: ignore[attr-defined]
            # Each stream has its own VADIterator (per-session state).
            assert stream_a._vad_iterator is not stream_b._vad_iterator  # type: ignore[attr-defined]


class TestAppContextEngines:
    """``AppContext`` carries the three shared engines."""

    def test_default_engine_fields_are_none(self) -> None:
        """When not provided, all three engine fields default to None."""
        from tank_backend.config.context import AppContext

        ctx = AppContext(app_config=MagicMock(name="AppConfig"))  # type: ignore[arg-type]

        assert ctx.asr_engine is None
        assert ctx.tts_engine is None
        assert ctx.vad_engine is None

    def test_engines_are_stored_and_shared(self) -> None:
        """Two AppContext copies built with the same engine instances
        carry the same object identity — sessions can share models."""
        from tank_backend.config.context import AppContext

        asr = _FakeASREngine()
        tts_mock = MagicMock(name="TTSEngine")
        vad_mock = MagicMock(name="VADEngine")
        app_config = MagicMock(name="AppConfig")

        ctx_a = AppContext(
            app_config=app_config,  # type: ignore[arg-type]
            asr_engine=asr,
            tts_engine=tts_mock,
            vad_engine=vad_mock,
        )
        ctx_b = AppContext(
            app_config=app_config,  # type: ignore[arg-type]
            asr_engine=asr,
            tts_engine=tts_mock,
            vad_engine=vad_mock,
        )

        assert ctx_a.asr_engine is ctx_b.asr_engine is asr
        assert ctx_a.tts_engine is ctx_b.tts_engine is tts_mock
        assert ctx_a.vad_engine is ctx_b.vad_engine is vad_mock
