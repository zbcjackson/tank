"""Tests for ASRSpeakerMerger."""

import asyncio

from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.asr_speaker_merger import ASRSpeakerMerger, SpeakerIDResult


async def _collect(merger, item):
    """Helper: process item through merger and return non-None outputs."""
    results = []
    async for _status, output in merger.process(item):
        if output is not None:
            results.append(output)
    return results


class TestASRSpeakerMerger:
    async def test_merge_asr_and_speaker_id(self):
        """When both branches report, merger emits BrainInputEvent with merged user."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0)

        asr_event = BrainInputEvent(
            type=InputType.AUDIO,
            text="hello",
            user="User",
            language="en",
            confidence=0.9,
            metadata={"msg_id": "m1", "utterance_id": "1.000_2.000"},
        )
        speaker_result = SpeakerIDResult(utterance_id="1.000_2.000", user_id="jackson")

        # Send ASR first — should not emit yet
        results = await _collect(merger, asr_event)
        assert results == []

        # Send speaker ID — should emit merged result
        results = await _collect(merger, speaker_result)
        assert len(results) == 1
        merged = results[0]
        assert merged.text == "hello"
        assert merged.user == "jackson"
        assert merged.metadata["utterance_id"] == "1.000_2.000"

    async def test_merge_speaker_id_first(self):
        """Order shouldn't matter — speaker ID arriving first should also work."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0)

        speaker_result = SpeakerIDResult(utterance_id="1.000_2.000", user_id="alice")
        asr_event = BrainInputEvent(
            type=InputType.AUDIO,
            text="hi",
            user="User",
            language="zh",
            confidence=0.8,
            metadata={"msg_id": "m2", "utterance_id": "1.000_2.000"},
        )

        # Send speaker ID first
        results = await _collect(merger, speaker_result)
        assert results == []

        # Send ASR — should emit
        results = await _collect(merger, asr_event)
        assert len(results) == 1
        assert results[0].user == "alice"
        assert results[0].text == "hi"

    async def test_passthrough_without_utterance_id(self):
        """BrainInputEvent without utterance_id should pass through unmodified."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0)

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="keyboard input",
            user="Keyboard",
            language=None,
            confidence=None,
            metadata={"msg_id": "kbd_1"},
        )

        results = await _collect(merger, event)
        assert len(results) == 1
        assert results[0] is event  # same object, not merged

    async def test_passthrough_unknown_type(self):
        """Unknown item types should pass through."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0)

        results = await _collect(merger, "some_string")
        assert results == ["some_string"]

    async def test_timeout_emits_partial_asr_only(self):
        """When speaker ID times out, merger should emit with default user."""
        merger = ASRSpeakerMerger(
            branch_count=2, timeout_s=0.05, timeout_multiplier=0,
            default_user="DefaultUser",
        )

        asr_event = BrainInputEvent(
            type=InputType.AUDIO,
            text="hello",
            user="User",
            language="en",
            confidence=0.9,
            metadata={"msg_id": "m3", "utterance_id": "3.000_4.000"},
        )

        # Send ASR only
        results = await _collect(merger, asr_event)
        assert results == []  # not yet — waiting for speaker ID

        # Wait for timeout
        await asyncio.sleep(0.1)

        # Next process call should expire the stale entry
        dummy = BrainInputEvent(
            type=InputType.AUDIO,
            text="next",
            user="User",
            language="en",
            confidence=0.9,
            metadata={"msg_id": "m4", "utterance_id": "5.000_6.000"},
        )
        await _collect(merger, dummy)

        # The timed-out entry should have been cleaned up
        assert "3.000_4.000" not in merger._pending

    async def test_speaker_id_only_discarded(self):
        """SpeakerIDResult without matching ASR should be discarded on timeout."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=0.05, timeout_multiplier=0)

        speaker_result = SpeakerIDResult(utterance_id="orphan_id", user_id="bob")
        await _collect(merger, speaker_result)

        assert "orphan_id" in merger._pending

        await asyncio.sleep(0.1)

        # Trigger expiry
        dummy = SpeakerIDResult(utterance_id="other", user_id="x")
        await _collect(merger, dummy)

        assert "orphan_id" not in merger._pending

    async def test_flush_clears_pending(self):
        """flush() should clear all pending state."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0)

        asr_event = BrainInputEvent(
            type=InputType.AUDIO,
            text="hello",
            user="User",
            language="en",
            confidence=0.9,
            metadata={"msg_id": "m5", "utterance_id": "7.000_8.000"},
        )
        await _collect(merger, asr_event)
        assert len(merger._pending) == 1

        merger.flush()
        assert len(merger._pending) == 0

    async def test_multiple_utterances_independent(self):
        """Multiple utterances should be tracked independently."""
        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0)

        asr1 = BrainInputEvent(
            type=InputType.AUDIO, text="first", user="User",
            language="en", confidence=0.9,
            metadata={"msg_id": "m1", "utterance_id": "1.000_2.000"},
        )
        asr2 = BrainInputEvent(
            type=InputType.AUDIO, text="second", user="User",
            language="en", confidence=0.9,
            metadata={"msg_id": "m2", "utterance_id": "3.000_4.000"},
        )
        spk1 = SpeakerIDResult(utterance_id="1.000_2.000", user_id="alice")
        spk2 = SpeakerIDResult(utterance_id="3.000_4.000", user_id="bob")

        await _collect(merger, asr1)
        await _collect(merger, asr2)
        assert len(merger._pending) == 2

        results = await _collect(merger, spk2)
        assert len(results) == 1
        assert results[0].text == "second"
        assert results[0].user == "bob"

        results = await _collect(merger, spk1)
        assert len(results) == 1
        assert results[0].text == "first"
        assert results[0].user == "alice"

        assert len(merger._pending) == 0

    async def test_bus_message_posted_on_merge(self):
        """Merger should post a bus message when merging."""
        bus = Bus()
        messages = []
        bus.subscribe("fan_in_merged", lambda m: messages.append(m))

        merger = ASRSpeakerMerger(branch_count=2, timeout_s=5.0, bus=bus)

        asr_event = BrainInputEvent(
            type=InputType.AUDIO, text="hello", user="User",
            language="en", confidence=0.9,
            metadata={"msg_id": "m1", "utterance_id": "1.000_2.000"},
        )
        speaker_result = SpeakerIDResult(utterance_id="1.000_2.000", user_id="jackson")

        await _collect(merger, asr_event)
        await _collect(merger, speaker_result)

        bus.poll()
        assert len(messages) == 1
        assert messages[0].payload["user"] == "jackson"
        assert messages[0].payload["had_speaker_id"] is True

    async def test_dynamic_timeout_scales_with_audio_duration(self):
        """Timeout should scale with audio duration: max(base, multiplier * duration)."""
        merger = ASRSpeakerMerger(
            branch_count=2, timeout_s=5.0, timeout_multiplier=3.0,
        )

        # Short utterance (1s audio) → timeout = max(5, 3*1) = 5s
        short_event = BrainInputEvent(
            type=InputType.AUDIO, text="hi", user="User",
            language="en", confidence=0.9,
            metadata={"msg_id": "m1", "utterance_id": "0.000_1.000"},
        )
        await _collect(merger, short_event)
        pending_short = merger._pending["0.000_1.000"]
        assert pending_short.audio_duration_s == 1.0
        assert merger._timeout_for(pending_short) == 5.0  # base wins

        # Long utterance (10s audio) → timeout = max(5, 3*10) = 30s
        long_event = BrainInputEvent(
            type=InputType.AUDIO, text="long speech", user="User",
            language="en", confidence=0.9,
            metadata={"msg_id": "m2", "utterance_id": "10.000_20.000"},
        )
        await _collect(merger, long_event)
        pending_long = merger._pending["10.000_20.000"]
        assert pending_long.audio_duration_s == 10.0
        assert merger._timeout_for(pending_long) == 30.0  # multiplier wins

    async def test_dynamic_timeout_fallback_for_unparseable_id(self):
        """Non-timestamp utterance_id should fall back to base timeout."""
        merger = ASRSpeakerMerger(
            branch_count=2, timeout_s=5.0, timeout_multiplier=3.0,
        )

        event = BrainInputEvent(
            type=InputType.AUDIO, text="hi", user="User",
            language="en", confidence=0.9,
            metadata={"msg_id": "m1", "utterance_id": "some_opaque_id"},
        )
        await _collect(merger, event)
        pending = merger._pending["some_opaque_id"]
        assert pending.audio_duration_s is None
        assert merger._timeout_for(pending) == 5.0  # base fallback
