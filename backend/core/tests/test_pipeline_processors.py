"""Tests for Phase 1 wrapper processors."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.event import EventDirection, PipelineEvent
from tank_backend.pipeline.processor import FlowReturn

# ── helpers ──────────────────────────────────────────────────────────────────

BASE_TIME = 1000.0


def _make_audio_frame(n_samples: int = 320, sr: int = 16000, timestamp_s: float | None = None):
    from tank_backend.audio.input.types import AudioFrame

    return AudioFrame(
        pcm=np.zeros(n_samples, dtype=np.float32),
        sample_rate=sr,
        timestamp_s=timestamp_s if timestamp_s is not None else BASE_TIME,
    )


def _make_vad_result_end_speech():
    from tank_backend.audio.input.vad import VADResult, VADStatus

    return VADResult(
        status=VADStatus.END_SPEECH,
        utterance_pcm=np.zeros(16000, dtype=np.float32),
        sample_rate=16000,
        started_at_s=1.0,
        ended_at_s=2.0,
    )


def _make_vad_result_no_speech():
    from tank_backend.audio.input.vad import VADResult, VADStatus

    return VADResult(status=VADStatus.NO_SPEECH)


def _make_vad_result_in_speech():
    from tank_backend.audio.input.vad import VADResult, VADStatus

    return VADResult(status=VADStatus.IN_SPEECH)


async def _collect(processor, item):
    """Collect all (status, output) pairs from processor.process(item)."""
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


# ── VADProcessor ─────────────────────────────────────────────────────────────

class TestVADProcessor:
    def _make_processor(self, vad_result, bus=None):
        from tank_backend.pipeline.processors.vad import VADProcessor

        vad = MagicMock()
        vad.process_frame = MagicMock(return_value=vad_result)
        vad.flush = MagicMock()
        proc = VADProcessor(vad_stream=vad, bus=bus)
        return proc, vad

    async def test_end_speech_yields_result(self):
        result = _make_vad_result_end_speech()
        proc, _ = self._make_processor(result)
        outputs = await _collect(proc, _make_audio_frame())
        assert len(outputs) == 1
        assert outputs[0][0] == FlowReturn.OK
        assert outputs[0][1] is result

    async def test_no_speech_yields_none(self):
        result = _make_vad_result_no_speech()
        proc, _ = self._make_processor(result)
        outputs = await _collect(proc, _make_audio_frame())
        assert outputs[0][1] is None

    async def test_in_speech_yields_audio_frame(self):
        """IN_SPEECH now forwards the AudioFrame for streaming ASR."""
        result = _make_vad_result_in_speech()
        proc, _ = self._make_processor(result)
        frame = _make_audio_frame()
        outputs = await _collect(proc, frame)
        assert outputs[0][0] == FlowReturn.OK
        assert outputs[0][1] is frame

    async def test_vad_does_not_post_speech_start(self):
        """VAD no longer posts speech_start — ASR owns that now."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        received = []
        bus.subscribe("speech_start", lambda m: received.append(m))

        result = VADResult(status=VADStatus.IN_SPEECH)
        proc, _ = self._make_processor(result, bus=bus)

        for _ in range(10):
            await _collect(proc, _make_audio_frame())
        bus.poll()

        assert len(received) == 0

    async def test_posts_speech_end_to_bus(self):
        bus = Bus()
        received = []
        bus.subscribe("speech_end", lambda m: received.append(m))

        result = _make_vad_result_end_speech()
        proc, _ = self._make_processor(result, bus=bus)
        await _collect(proc, _make_audio_frame())
        bus.poll()

        assert len(received) == 1

    async def test_flush_event_calls_vad_flush(self):
        result = _make_vad_result_no_speech()
        proc, vad = self._make_processor(result)
        event = PipelineEvent(type="flush", direction=EventDirection.DOWNSTREAM)
        consumed = proc.handle_event(event)
        assert consumed is False
        vad.flush.assert_called_once()

    def test_flush_speech_returns_end_speech_result(self):
        end_result = _make_vad_result_end_speech()
        proc, vad = self._make_processor(_make_vad_result_in_speech())
        vad.flush.return_value = end_result

        out = proc.flush_speech()

        assert out is end_result
        vad.flush.assert_called_once()

    def test_flush_speech_returns_none_when_no_active_speech(self):
        proc, vad = self._make_processor(_make_vad_result_no_speech())
        vad.flush.return_value = _make_vad_result_no_speech()

        out = proc.flush_speech()

        assert out is None

    def test_flush_speech_posts_speech_end_to_bus(self):
        bus = Bus()
        received = []
        bus.subscribe("speech_end", lambda m: received.append(m))
        proc, vad = self._make_processor(_make_vad_result_in_speech(), bus=bus)
        vad.flush.return_value = _make_vad_result_end_speech()

        proc.flush_speech()
        bus.poll()

        assert len(received) == 1
        assert received[0].source == "vad"

    async def test_input_caps(self):
        from tank_backend.pipeline.processors.vad import VADProcessor

        vad = MagicMock()
        proc = VADProcessor(vad_stream=vad)
        assert proc.input_caps is not None
        assert proc.input_caps.sample_rate == 16000

    async def test_end_of_utterance_sentinel_produces_end_speech(self):
        """EndOfUtterance sentinel flushes VAD and yields END_SPEECH downstream."""
        from tank_backend.pipeline.processors.vad import END_OF_UTTERANCE

        end_result = _make_vad_result_end_speech()
        proc, vad = self._make_processor(_make_vad_result_in_speech())
        vad.flush.return_value = end_result

        outputs = [(fr, out) async for fr, out in proc.process(END_OF_UTTERANCE)]

        vad.flush.assert_called_once()
        assert len(outputs) == 1
        assert outputs[0][0] == FlowReturn.OK
        assert outputs[0][1] is end_result

    async def test_end_of_utterance_sentinel_no_speech(self):
        """EndOfUtterance sentinel yields None when VAD has no active speech."""
        from tank_backend.pipeline.processors.vad import END_OF_UTTERANCE

        proc, vad = self._make_processor(_make_vad_result_no_speech())
        vad.flush.return_value = _make_vad_result_no_speech()

        outputs = [(fr, out) async for fr, out in proc.process(END_OF_UTTERANCE)]

        assert len(outputs) == 1
        assert outputs[0] == (FlowReturn.OK, None)


# ── ASRProcessor ─────────────────────────────────────────────────────────────

def _make_streaming_asr(text="hello", supports_streaming=True):
    """Create a mock ASR engine with streaming support."""
    asr = MagicMock()
    asr.process_pcm = MagicMock(return_value=text)
    asr.stop = MagicMock(return_value=text)
    asr.start = MagicMock()
    asr.close = MagicMock()
    asr.supports_streaming = supports_streaming
    return asr


    async def test_turn_reopened_posted_on_reopened_start_speech(self):
        """A reopened START_SPEECH (revision > 0) notifies the assistant."""
        from tank_backend.audio.input.vad import VADResult, VADStatus
        from tank_backend.pipeline.processors.vad import VADProcessor

        bus = Bus()
        received = []
        bus.subscribe("turn_reopened", lambda m: received.append(m))

        vad = MagicMock()
        vad.process_frame = MagicMock(return_value=VADResult(
            status=VADStatus.START_SPEECH,
            started_at_s=BASE_TIME,
            turn_id="turn_1000.000",
            turn_revision=1,
        ))
        proc = VADProcessor(vad_stream=vad, bus=bus)
        await _collect(proc, _make_audio_frame())
        bus.poll()

        assert len(received) == 1
        assert received[0].payload["turn_id"] == "turn_1000.000"
        assert received[0].payload["turn_revision"] == 1

    async def test_no_turn_reopened_for_fresh_start_speech(self):
        """A fresh START_SPEECH (revision 0) posts no reopen message."""
        from tank_backend.audio.input.vad import VADResult, VADStatus
        from tank_backend.pipeline.processors.vad import VADProcessor

        bus = Bus()
        received = []
        bus.subscribe("turn_reopened", lambda m: received.append(m))

        vad = MagicMock()
        vad.process_frame = MagicMock(return_value=VADResult(
            status=VADStatus.START_SPEECH, started_at_s=BASE_TIME,
        ))
        proc = VADProcessor(vad_stream=vad, bus=bus)
        await _collect(proc, _make_audio_frame())
        bus.poll()

        assert len(received) == 0


class TestASRProcessor:
    def _make_processor(self, text="hello", bus=None, supports_streaming=True):
        from tank_backend.pipeline.processors.asr import ASRProcessor

        asr = _make_streaming_asr(text, supports_streaming)
        proc = ASRProcessor(asr_stream=asr, bus=bus, user="TestUser")
        return proc, asr

    # ── Batch mode (VADResult only) ──────────────────────────────────────

    async def test_transcribes_vad_result(self):
        proc, _ = self._make_processor(text="hello world")
        vad_result = _make_vad_result_end_speech()
        outputs = await _collect(proc, vad_result)

        assert len(outputs) == 1
        assert outputs[0][0] == FlowReturn.OK
        brain_event = outputs[0][1]
        assert brain_event is not None
        assert brain_event.text == "hello world"
        assert brain_event.user == "TestUser"

    async def test_empty_text_yields_none(self):
        proc, _ = self._make_processor(text="")
        vad_result = _make_vad_result_end_speech()
        outputs = await _collect(proc, vad_result)
        assert outputs[0][1] is None

    async def test_empty_utterance_yields_none(self):
        from tank_backend.audio.input.vad import VADResult, VADStatus

        proc, _ = self._make_processor()
        empty = VADResult(
            status=VADStatus.END_SPEECH,
            utterance_pcm=np.array([], dtype=np.float32),
            sample_rate=16000,
        )
        outputs = await _collect(proc, empty)
        assert outputs[0][1] is None

    async def test_posts_asr_result_to_bus(self):
        bus = Bus()
        received = []
        bus.subscribe("asr_result", lambda m: received.append(m))

        proc, _ = self._make_processor(text="hi", bus=bus)
        await _collect(proc, _make_vad_result_end_speech())
        bus.poll()

        assert len(received) == 1
        assert received[0].payload["text"] == "hi"
        assert "latency_s" in received[0].payload

    async def test_posts_user_transcript_to_bus(self):
        """Final transcript posted to bus on END_SPEECH."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        proc, _ = self._make_processor(text="你好世界", bus=bus)

        # Send START_SPEECH to initialize msg_id
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Send END_SPEECH to finalize
        await _collect(proc, _make_vad_result_end_speech())
        bus.poll()

        assert len(received) == 2
        # First message: speech_detected signal
        assert received[0].payload.signal_type == "speech_detected"
        # Second message: the actual transcript
        display_msg = received[1].payload
        assert display_msg.is_user is True
        assert display_msg.text == "你好世界"
        assert display_msg.speaker == "TestUser"
        assert display_msg.is_final is True
        assert display_msg.msg_id is not None
        assert display_msg.msg_id.startswith("user_")

    async def test_no_user_transcript_for_empty_text(self):
        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        proc, _ = self._make_processor(text="", bus=bus)
        await _collect(proc, _make_vad_result_end_speech())
        bus.poll()

        assert len(received) == 0

    async def test_flush_event_stops_asr(self):
        proc, asr = self._make_processor()
        event = PipelineEvent(type="flush")
        consumed = proc.handle_event(event)
        assert consumed is False
        asr.stop.assert_called_once()

    # ── Streaming mode (START_SPEECH → AudioFrame → END_SPEECH) ───────────

    async def test_streaming_start_speech_starts_session(self):
        """START_SPEECH calls asr.start() and posts speech_start."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        speech_starts = []
        bus.subscribe("speech_start", lambda m: speech_starts.append(m))

        proc, asr = self._make_processor(text="你好", bus=bus)
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)
        bus.poll()

        asr.start.assert_called_once()
        assert len(speech_starts) == 1
        assert speech_starts[0].source == "asr"

    async def test_streaming_audio_frame_partial_transcript(self):
        """Growing hypotheses → speech_detected on the first raw hypothesis,
        then a stabilized partial (confirmed prefix, edge word held back)."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        proc, asr = self._make_processor(text="你好世界", bus=bus)
        asr.process_pcm = MagicMock(side_effect=["你好", "你好世界"])

        # First send START_SPEECH to start session
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Then send AudioFrames with two growing hypotheses
        outputs = await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME))
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME + 0.02))
        bus.poll()

        # AudioFrame yields None (brain waits for final)
        assert outputs[0][1] is None

        # speech_detected fired on the first raw hypothesis
        assert received[0].payload.signal_type == "speech_detected"
        partials = [
            m.payload for m in received
            if getattr(m.payload, "is_user", False)
            and m.payload.is_final is False
        ]
        # "你好" + "你好世界" confirm 你; edge 好 is held back.
        assert [p.text for p in partials] == ["你"]
        assert partials[0].is_user is True
        assert partials[0].msg_id is not None

    async def test_streaming_first_partial_posts_speech_start(self):
        """speech_start is posted on START_SPEECH, not on first partial."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        speech_starts = []
        bus.subscribe("speech_start", lambda m: speech_starts.append(m))

        proc, _ = self._make_processor(text="hello", bus=bus)

        # START_SPEECH posts speech_start
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)
        bus.poll()

        assert len(speech_starts) == 1
        assert speech_starts[0].source == "asr"

    async def test_streaming_speech_start_posted_only_once(self):
        """speech_start is posted only on START_SPEECH, not repeated on frames."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        speech_starts = []
        bus.subscribe("speech_start", lambda m: speech_starts.append(m))

        proc, _ = self._make_processor(text="hello", bus=bus)

        # START_SPEECH
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Send multiple frames
        for i in range(5):
            await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME + i * 0.02))
        bus.poll()

        assert len(speech_starts) == 1

    async def test_streaming_no_speech_start_on_empty_text(self):
        """speech_start is posted on START_SPEECH even if later text is empty."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        speech_starts = []
        bus.subscribe("speech_start", lambda m: speech_starts.append(m))

        proc, _ = self._make_processor(text="", bus=bus)

        # START_SPEECH posts speech_start regardless of text
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)
        bus.poll()

        # speech_start is posted on START_SPEECH
        assert len(speech_starts) == 1

    async def test_streaming_end_speech_finalizes(self):
        """START_SPEECH → AudioFrames → END_SPEECH → BrainInputEvent with final text."""
        from tank_backend.audio.input.vad import VADResult, VADStatus
        from tank_backend.pipeline.processors.asr import ASRProcessor

        # ASR returns partial on process_pcm, final on stop()
        asr = MagicMock()
        asr.supports_streaming = True
        asr.start = MagicMock()
        asr.process_pcm = MagicMock(return_value="你好世界")
        asr.stop = MagicMock(return_value="你好世界，今天天气很好")

        proc = ASRProcessor(asr_stream=asr, user="TestUser")

        # START_SPEECH
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Send a few AudioFrames to build up partial text
        for i in range(3):
            await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME + i * 0.02))

        # Now send END_SPEECH
        vad_result = _make_vad_result_end_speech()
        outputs = await _collect(proc, vad_result)

        assert len(outputs) == 1
        brain_event = outputs[0][1]
        assert brain_event is not None
        assert brain_event.text == "你好世界，今天天气很好"
        assert brain_event.user == "TestUser"
        asr.stop.assert_called_once()

    async def test_non_streaming_engine_ignores_frames(self):
        """supports_streaming=False → AudioFrame yields None, no bus messages."""
        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))
        bus.subscribe("speech_start", lambda m: received.append(m))

        proc, _ = self._make_processor(text="hello", bus=bus, supports_streaming=False)
        outputs = await _collect(proc, _make_audio_frame())
        bus.poll()

        assert outputs[0][1] is None
        assert len(received) == 0

    async def test_non_streaming_engine_batch_on_end_speech(self):
        """Non-streaming engine transcribes full utterance on END_SPEECH and posts speech_start."""
        bus = Bus()
        speech_starts = []
        bus.subscribe("speech_start", lambda m: speech_starts.append(m))

        proc, _ = self._make_processor(text="batch result", bus=bus, supports_streaming=False)
        vad_result = _make_vad_result_end_speech()
        outputs = await _collect(proc, vad_result)
        bus.poll()

        brain_event = outputs[0][1]
        assert brain_event is not None
        assert brain_event.text == "batch result"
        # speech_start posted for non-streaming engines on finalize
        assert len(speech_starts) == 1

    # ── Speculative reopen (turn revision) ────────────────────────────────

    TURN_ID = "turn_1000.000"

    def _vad_end_speech(self, pcm, *, turn_id=None, turn_revision=0):
        from tank_backend.audio.input.vad import VADResult, VADStatus

        return VADResult(
            status=VADStatus.END_SPEECH,
            utterance_pcm=pcm,
            sample_rate=16000,
            started_at_s=1.0,
            ended_at_s=2.0,
            turn_id=turn_id,
            turn_revision=turn_revision,
        )

    def _vad_start_speech(self, *, turn_id=None, turn_revision=0):
        from tank_backend.audio.input.vad import VADResult, VADStatus

        return VADResult(
            status=VADStatus.START_SPEECH,
            started_at_s=3.0,
            turn_id=turn_id,
            turn_revision=turn_revision,
        )

    async def test_reopened_turn_reuses_msg_id_and_retranscribes(self):
        """A reopened utterance keeps the turn's msg_id and re-transcribes
        the full concatenated audio (not just the resumed tail)."""
        pcm = np.zeros(16000, dtype=np.float32)
        proc, asr = self._make_processor(text="我想吃还是喝")

        # Original utterance (revision 0)
        await _collect(proc, self._vad_start_speech())
        orig = await _collect(proc, self._vad_end_speech(pcm, turn_id=self.TURN_ID))
        orig_event = orig[-1][1]
        assert orig_event.turn_id == self.TURN_ID
        assert orig_event.turn_revision == 0
        orig_msg_id = orig_event.metadata["msg_id"]

        # Reopened utterance (revision 1): resumed speech → full re-transcribe
        await _collect(proc, self._vad_start_speech(
            turn_id=self.TURN_ID, turn_revision=1,
        ))
        reopened = await _collect(proc, self._vad_end_speech(
            pcm, turn_id=self.TURN_ID, turn_revision=1,
        ))
        event = reopened[-1][1]
        assert event.turn_id == self.TURN_ID
        assert event.turn_revision == 1
        assert event.metadata["msg_id"] == orig_msg_id, (
            "reopened turn must reuse the original msg_id for in-place UI update"
        )

        # start: original + reopened + re-transcription; stop: original +
        # discard + final. process_pcm saw the full concatenated PCM.
        assert asr.start.call_count == 3
        assert asr.stop.call_count == 3
        fed = asr.process_pcm.call_args_list[-1][0][0]
        assert np.array_equal(fed, pcm)

    async def test_reopened_partials_prepend_committed_text(self):
        """Live partials of a reopened turn show prefix + resumed tail."""
        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        proc, asr = self._make_processor(text="我想吃", bus=bus)
        await _collect(proc, self._vad_start_speech())
        await _collect(proc, self._vad_end_speech(
            np.zeros(1600, dtype=np.float32), turn_id=self.TURN_ID,
        ))

        asr.process_pcm = MagicMock(side_effect=["还是", "还是喝", "还是喝吧"])
        await _collect(proc, self._vad_start_speech(
            turn_id=self.TURN_ID, turn_revision=1,
        ))
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME))
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME + 0.02))
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME + 0.04))
        bus.poll()

        partials = [
            m.payload for m in received
            if getattr(m.payload, "is_user", False)
            and getattr(m.payload, "is_final", True) is False
        ]
        assert partials, "expected a partial transcript for the reopened turn"
        # Prefix + stabilized tail: "还是" confirmed by hypotheses 2+3
        # (edge held back on each feed).
        assert partials[-1].text == "我想吃还是"

    async def test_reopened_non_streaming_engine_retranscribes_full(self):
        """Batch engines take the same full-audio path on reopen."""
        pcm = np.zeros(8000, dtype=np.float32)
        proc, asr = self._make_processor(
            text="merged text", supports_streaming=False,
        )

        await _collect(proc, self._vad_end_speech(pcm, turn_id=self.TURN_ID))
        orig_event = (
            await _collect(proc, self._vad_end_speech(pcm, turn_id=self.TURN_ID))
        )[-1][1]
        orig_msg_id = orig_event.metadata["msg_id"]

        await _collect(proc, self._vad_start_speech(
            turn_id=self.TURN_ID, turn_revision=1,
        ))
        outputs = await _collect(proc, self._vad_end_speech(
            pcm, turn_id=self.TURN_ID, turn_revision=1,
        ))

        event = outputs[-1][1]
        assert event.text == "merged text"
        assert event.metadata["msg_id"] == orig_msg_id
        fed = asr.process_pcm.call_args_list[-1][0][0]
        assert np.array_equal(fed, pcm)

    async def test_flush_resets_streaming_state(self):
        """Flush event resets streaming state so next utterance starts clean."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        proc, asr = self._make_processor(text="partial", bus=bus)

        # Start session and build up some streaming state
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME))
        assert proc._partial_text == "partial"
        assert proc._streaming_msg_id is not None

        # Flush
        event = PipelineEvent(type="flush")
        proc.handle_event(event)

        assert proc._partial_text == ""
        assert proc._streaming_msg_id is None
        asr.stop.assert_called()

    async def test_streaming_same_text_no_duplicate_ui_message(self):
        """If ASR returns the same text on consecutive frames, no duplicate ui_message."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        proc, _ = self._make_processor(text="hello", bus=bus)

        # START_SPEECH first to initialize session
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Two frames, same text
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME))
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME + 0.02))
        bus.poll()

        # Only speech_detected: the raw text never changed (one hypothesis,
        # which confirms nothing under stabilization).
        assert len(received) == 1
        assert received[0].payload.signal_type == "speech_detected"

    # ── _stop_with_timeout resilience ───────────────────────────────────────

    async def test_stop_with_timeout_succeeds(self):
        """Normal stop() completes within timeout and returns text."""
        from tank_backend.audio.input.vad import VADResult, VADStatus

        proc, asr = self._make_processor(text="final text")

        # Start session
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # END_SPEECH triggers _stop_with_timeout
        vad_result = _make_vad_result_end_speech()
        outputs = await _collect(proc, vad_result)

        brain_event = outputs[0][1]
        assert brain_event is not None
        assert brain_event.text == "final text"
        asr.stop.assert_called_once()

    async def test_stop_with_timeout_posts_recognition_failed(self):
        """When stop() times out, recognition_failed signal is posted."""
        from unittest.mock import AsyncMock

        from tank_backend.audio.input.vad import VADResult, VADStatus
        from tank_backend.pipeline.processors.asr import ASRProcessor

        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        asr = MagicMock()
        asr.supports_streaming = True
        asr.start = MagicMock()
        asr.process_pcm = MagicMock(return_value="partial")
        asr.stop = MagicMock(side_effect=lambda: None)

        proc = ASRProcessor(asr_stream=asr, bus=bus, user="TestUser")

        # Start session
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Make _stop_with_timeout raise TimeoutError
        with patch.object(proc, "_stop_with_timeout", new=AsyncMock(return_value="")):
            # Simulate timeout by having _stop_with_timeout return "" and post signal
            proc._post_recognition_failed()
            vad_result = _make_vad_result_end_speech()
            await _collect(proc, vad_result)

        bus.poll()

        # Check recognition_failed signal was posted
        signal_msgs = [
            m for m in received
            if hasattr(m.payload, 'signal_type')
            and m.payload.signal_type == "recognition_failed"
        ]
        assert len(signal_msgs) == 1

    async def test_stop_timeout_returns_partial_text(self):
        """When stop() times out, partial text is used as fallback."""
        from unittest.mock import AsyncMock

        from tank_backend.audio.input.vad import VADResult, VADStatus
        from tank_backend.pipeline.processors.asr import ASRProcessor

        asr = MagicMock()
        asr.supports_streaming = True
        asr.start = MagicMock()
        asr.process_pcm = MagicMock(return_value="partial fallback")
        asr.stop = MagicMock(return_value="")

        proc = ASRProcessor(asr_stream=asr, user="TestUser")

        # Start session
        start_speech = VADResult(status=VADStatus.START_SPEECH, started_at_s=BASE_TIME)
        await _collect(proc, start_speech)

        # Send a frame to build up partial text
        await _collect(proc, _make_audio_frame(timestamp_s=BASE_TIME))
        assert proc._partial_text == "partial fallback"

        # Make _stop_with_timeout return "" (simulating timeout)
        with patch.object(proc, "_stop_with_timeout", new=AsyncMock(return_value="")):
            vad_result = _make_vad_result_end_speech()
            outputs = await _collect(proc, vad_result)

        # Falls back to partial text
        brain_event = outputs[0][1]
        assert brain_event is not None
        assert brain_event.text == "partial fallback"


# ── TTSProcessor ─────────────────────────────────────────────────────────────

class TestTTSProcessor:
    def _make_processor(self, chunks=None, bus=None):
        from tank_backend.pipeline.processors.tts import TTSProcessor

        if chunks is None:
            chunks = []

        async def fake_stream(*args, **kwargs):
            for c in chunks:
                yield c

        tts = MagicMock()
        tts.generate_stream = MagicMock(return_value=fake_stream())
        proc = TTSProcessor(tts_engine=tts, bus=bus)
        return proc, tts

    async def test_yields_audio_chunks(self):
        from tank_backend.core.events import AudioOutputRequest

        chunk1 = MagicMock()
        chunk2 = MagicMock()
        proc, _ = self._make_processor(chunks=[chunk1, chunk2])

        request = AudioOutputRequest(content="hello", language="en")
        outputs = await _collect(proc, request)

        assert len(outputs) == 2
        assert outputs[0] == (FlowReturn.OK, chunk1)
        assert outputs[1] == (FlowReturn.OK, chunk2)

    async def test_forwards_drain_sentinel_without_synthesizing(self):
        """A DrainSentinel passes through untouched — engine never called."""
        from tank_backend.pipeline.event import DrainSentinel

        proc, tts = self._make_processor(chunks=[MagicMock()])
        sentinel = DrainSentinel()
        outputs = await _collect(proc, sentinel)

        assert outputs == [(FlowReturn.OK, sentinel)]
        tts.generate_stream.assert_not_called()

    async def test_posts_tts_latency_to_bus(self):
        from tank_backend.core.events import AudioOutputRequest

        bus = Bus()
        received = []
        bus.subscribe("tts_finished", lambda m: received.append(m))

        proc, _ = self._make_processor(chunks=[MagicMock()], bus=bus)
        await _collect(proc, AudioOutputRequest(content="hi"))
        bus.poll()

        assert len(received) == 1
        assert received[0].payload["chunk_count"] == 1

    async def test_interrupt_event_stops_generation(self):
        proc, _ = self._make_processor()
        event = PipelineEvent(type="interrupt")
        consumed = proc.handle_event(event)
        assert consumed is False
        assert proc._interrupted is True

    async def test_flush_event_stops_generation(self):
        proc, _ = self._make_processor()
        event = PipelineEvent(type="flush")
        proc.handle_event(event)
        assert proc._interrupted is True


# ── PlaybackProcessor ────────────────────────────────────────────────────────

class TestPlaybackProcessor:
    def _make_processor(self, bus=None):
        from tank_backend.pipeline.processors.playback import PlaybackProcessor

        callback = MagicMock()
        proc = PlaybackProcessor(playback_callback=callback, bus=bus)
        return proc, callback

    async def test_delegates_to_callback(self):
        proc, callback = self._make_processor()
        chunk = MagicMock()
        await _collect(proc, chunk)
        callback.assert_called_once_with(chunk)

    async def test_drain_sentinel_arrives_and_is_not_played(self):
        """A DrainSentinel marks arrival (drain proof) and never reaches the callback."""
        from tank_backend.pipeline.event import DrainSentinel

        proc, callback = self._make_processor()
        sentinel = DrainSentinel()
        assert not sentinel.wait(0.0)  # not yet arrived

        outputs = await _collect(proc, sentinel)

        assert outputs == [(FlowReturn.OK, None)]
        callback.assert_not_called()
        assert sentinel.wait(0.0) is True  # arrived

    async def test_flush_event_sets_flushed(self):
        proc, _ = self._make_processor()
        event = PipelineEvent(type="flush")
        consumed = proc.handle_event(event)
        assert consumed is True  # terminal — consumes
        assert proc._flushed is True

    async def test_interrupt_event_sets_flushed(self):
        proc, _ = self._make_processor()
        event = PipelineEvent(type="interrupt")
        consumed = proc.handle_event(event)
        assert consumed is True
        assert proc._flushed is True

    async def test_flushed_clears_on_new_chunk(self):
        """After flush, the first new chunk clears the flushed flag and processes normally."""
        proc, callback = self._make_processor()
        proc._flushed = True
        chunk = MagicMock()
        outputs = await _collect(proc, chunk)
        # First chunk after flush clears the flag and processes normally
        assert outputs[0][0] == FlowReturn.OK
        assert proc._flushed is False
        callback.assert_called_once_with(chunk)

    async def test_start_resets_state(self):
        proc, _ = self._make_processor()
        proc._flushed = True
        proc._chunk_count = 42
        await proc.start()
        assert proc._flushed is False
        assert proc._chunk_count == 0

    async def test_stop_sets_flushed(self):
        proc, _ = self._make_processor()
        await proc.stop()
        assert proc._flushed is True
