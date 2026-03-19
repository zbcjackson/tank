"""Tests for SpeakerIDProcessor."""

from unittest.mock import MagicMock

import numpy as np

from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.asr_speaker_merger import SpeakerIDResult
from tank_backend.pipeline.processors.speaker_id import SpeakerIDProcessor


def _make_vad_result(status_name="END_SPEECH", pcm=None, sr=16000, start=1.0, end=2.0):
    """Build a VADResult without importing the real enum at module level."""
    from tank_backend.audio.input.vad import VADResult, VADStatus

    status = getattr(VADStatus, status_name)
    if pcm is None and status_name == "END_SPEECH":
        pcm = np.random.randn(16000).astype(np.float32)
    return VADResult(
        status=status,
        utterance_pcm=pcm,
        sample_rate=sr,
        started_at_s=start,
        ended_at_s=end,
    )


async def _collect(proc, item):
    results = []
    async for _status, output in proc.process(item):
        if output is not None:
            results.append(output)
    return results


class TestSpeakerIDProcessor:
    async def test_produces_speaker_id_result(self):
        """SpeakerIDProcessor should emit SpeakerIDResult for END_SPEECH VADResult."""
        recognizer = MagicMock()
        recognizer.identify.return_value = "jackson"

        proc = SpeakerIDProcessor(recognizer=recognizer)
        vad_result = _make_vad_result(start=1.5, end=3.0)

        results = await _collect(proc, vad_result)

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, SpeakerIDResult)
        assert result.utterance_id == "1.500_3.000"
        assert result.user_id == "jackson"
        recognizer.identify.assert_called_once()

    async def test_ignores_non_end_speech(self):
        """SpeakerIDProcessor should ignore IN_SPEECH and NO_SPEECH VADResults."""
        recognizer = MagicMock()
        proc = SpeakerIDProcessor(recognizer=recognizer)

        for status in ("IN_SPEECH", "NO_SPEECH"):
            vad_result = _make_vad_result(status_name=status, pcm=None, start=None, end=None)
            results = await _collect(proc, vad_result)
            assert results == []

        recognizer.identify.assert_not_called()

    async def test_ignores_empty_pcm(self):
        """SpeakerIDProcessor should ignore END_SPEECH with empty PCM."""
        recognizer = MagicMock()
        proc = SpeakerIDProcessor(recognizer=recognizer)

        vad_result = _make_vad_result(pcm=np.array([], dtype=np.float32))
        results = await _collect(proc, vad_result)
        assert results == []
        recognizer.identify.assert_not_called()

    async def test_ignores_non_vad_input(self):
        """SpeakerIDProcessor should ignore non-VADResult input."""
        recognizer = MagicMock()
        proc = SpeakerIDProcessor(recognizer=recognizer)

        results = await _collect(proc, "not_a_vad_result")
        assert results == []
        recognizer.identify.assert_not_called()

    async def test_posts_bus_message(self):
        """SpeakerIDProcessor should post speaker_id_result to bus."""
        bus = Bus()
        messages = []
        bus.subscribe("speaker_id_result", lambda m: messages.append(m))

        recognizer = MagicMock()
        recognizer.identify.return_value = "alice"

        proc = SpeakerIDProcessor(recognizer=recognizer, bus=bus)
        vad_result = _make_vad_result(start=2.0, end=4.0)

        await _collect(proc, vad_result)
        bus.poll()

        assert len(messages) == 1
        assert messages[0].payload["user_id"] == "alice"
        assert messages[0].payload["utterance_id"] == "2.000_4.000"

    async def test_utterance_id_matches_asr_format(self):
        """utterance_id format should match ASRProcessor's format exactly."""
        recognizer = MagicMock()
        recognizer.identify.return_value = "user1"

        proc = SpeakerIDProcessor(recognizer=recognizer)
        vad_result = _make_vad_result(start=10.123, end=12.456)

        results = await _collect(proc, vad_result)
        assert results[0].utterance_id == "10.123_12.456"
