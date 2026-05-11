"""Unit tests for :mod:`tank_backend.connectors.voice_bridge`.

Exercises the pydub+ffmpeg round-trip with tiny synthetic audio: encode a
sine wave as Ogg/Opus, feed it back through the decoder, and check that
the shape + sample rate line up. Also covers the concat helper and all
the error paths.
"""

from __future__ import annotations

import io
import shutil

import numpy as np
import pytest
from pydub import AudioSegment
from tank_contracts.tts import AudioChunk

from tank_backend.connectors.voice_bridge import (
    VoiceBridgeError,
    concat_audio_chunks,
    decode_ogg_opus,
    encode_pcm_to_opus,
)

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None
_needs_ffmpeg = pytest.mark.skipif(
    not _HAVE_FFMPEG,
    reason="ffmpeg not on PATH — voice bridge tests require it",
)


def _sine_pcm_bytes(
    *,
    duration_s: float = 0.5,
    frequency: float = 440.0,
    sample_rate: int = 16000,
    channels: int = 1,
    amplitude: float = 0.4,
) -> bytes:
    """Generate ``duration_s`` of a mono sine tone as int16 LE bytes."""
    n = int(duration_s * sample_rate)
    t = np.arange(n, dtype=np.float32) / sample_rate
    signal = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
    int16 = (signal * 32767).astype("<i2")
    if channels == 2:
        int16 = np.stack([int16, int16], axis=-1).flatten()
    return int16.tobytes()


def _ogg_opus_bytes_from_pcm(
    pcm: bytes, *, sample_rate: int = 16000, channels: int = 1,
) -> bytes:
    """Build Ogg/Opus bytes via pydub — used as test input to the decoder."""
    seg = AudioSegment(
        data=pcm,
        sample_width=2,
        frame_rate=sample_rate,
        channels=channels,
    )
    out = io.BytesIO()
    seg.export(out, format="ogg", codec="libopus")
    return out.getvalue()


# ---------------------------------------------------------------------------
# decode_ogg_opus
# ---------------------------------------------------------------------------


class TestDecodeOggOpus:
    @_needs_ffmpeg
    def test_roundtrip_sine_wave(self) -> None:
        pcm = _sine_pcm_bytes(duration_s=0.5, sample_rate=48000)
        ogg = _ogg_opus_bytes_from_pcm(pcm, sample_rate=48000)

        out = decode_ogg_opus(ogg)

        assert out.dtype == np.float32
        assert out.ndim == 1
        # 16 kHz × 0.5 s = 8000 samples. Opus encoding pads slightly; give
        # a ±2% tolerance so we're not hostage to codec framing.
        assert 7800 <= out.size <= 8200
        # Amplitude should survive — not bit-identical (lossy codec),
        # but roughly in the original 0.4 range.
        assert 0.1 < np.abs(out).max() < 1.0

    @_needs_ffmpeg
    def test_resamples_48khz_input_to_16khz(self) -> None:
        pcm = _sine_pcm_bytes(duration_s=1.0, sample_rate=48000)
        ogg = _ogg_opus_bytes_from_pcm(pcm, sample_rate=48000)

        out = decode_ogg_opus(ogg)
        # 1 second at 16 kHz = 16000 samples, with codec framing tolerance.
        assert 15600 <= out.size <= 16400

    @_needs_ffmpeg
    def test_downmixes_stereo_to_mono(self) -> None:
        pcm = _sine_pcm_bytes(duration_s=0.3, sample_rate=48000, channels=2)
        ogg = _ogg_opus_bytes_from_pcm(pcm, sample_rate=48000, channels=2)

        out = decode_ogg_opus(ogg)
        # Still 1-D (mono) after decode.
        assert out.ndim == 1

    def test_empty_payload_raises(self) -> None:
        with pytest.raises(VoiceBridgeError, match="empty"):
            decode_ogg_opus(b"")

    @_needs_ffmpeg
    def test_garbage_payload_raises_user_friendly_error(self) -> None:
        with pytest.raises(VoiceBridgeError, match="decode failed"):
            decode_ogg_opus(b"not an ogg file, just random bytes" * 100)


# ---------------------------------------------------------------------------
# encode_pcm_to_opus
# ---------------------------------------------------------------------------


class TestEncodePcmToOpus:
    @_needs_ffmpeg
    def test_produces_valid_ogg_header(self) -> None:
        pcm = _sine_pcm_bytes(duration_s=0.5, sample_rate=24000)

        ogg = encode_pcm_to_opus(pcm, sample_rate=24000)

        assert len(ogg) > 0
        # Ogg magic.
        assert ogg.startswith(b"OggS")

    @_needs_ffmpeg
    def test_roundtrip_through_decoder(self) -> None:
        pcm = _sine_pcm_bytes(duration_s=0.5, sample_rate=24000)

        ogg = encode_pcm_to_opus(pcm, sample_rate=24000)
        decoded = decode_ogg_opus(ogg)

        # 16 kHz output from the decoder, 0.5 s ≈ 8000 samples.
        assert 7800 <= decoded.size <= 8200

    @_needs_ffmpeg
    def test_handles_non_opus_native_rate(self) -> None:
        """Opus's native rates are 8/12/16/24/48 kHz; ffmpeg resamples
        whatever we give it. 22050 (common MP3 rate) should still work."""
        pcm = _sine_pcm_bytes(duration_s=0.3, sample_rate=22050)
        ogg = encode_pcm_to_opus(pcm, sample_rate=22050)
        assert ogg.startswith(b"OggS")

    def test_empty_pcm_raises(self) -> None:
        with pytest.raises(VoiceBridgeError, match="empty PCM"):
            encode_pcm_to_opus(b"", sample_rate=24000)

    def test_invalid_sample_rate_raises(self) -> None:
        with pytest.raises(VoiceBridgeError, match="invalid sample_rate"):
            encode_pcm_to_opus(b"\x00\x00" * 100, sample_rate=0)


# ---------------------------------------------------------------------------
# concat_audio_chunks
# ---------------------------------------------------------------------------


class TestConcatAudioChunks:
    def test_single_chunk(self) -> None:
        chunk = AudioChunk(data=b"\x01\x02\x03\x04", sample_rate=24000, channels=1)
        pcm, sr = concat_audio_chunks([chunk])
        assert pcm == b"\x01\x02\x03\x04"
        assert sr == 24000

    def test_multiple_chunks_concatenate_in_order(self) -> None:
        chunks = [
            AudioChunk(data=b"\x01\x02", sample_rate=24000, channels=1),
            AudioChunk(data=b"\x03\x04", sample_rate=24000, channels=1),
            AudioChunk(data=b"\x05\x06", sample_rate=24000, channels=1),
        ]
        pcm, sr = concat_audio_chunks(chunks)
        assert pcm == b"\x01\x02\x03\x04\x05\x06"
        assert sr == 24000

    def test_empty_list_raises(self) -> None:
        with pytest.raises(VoiceBridgeError, match="no chunks"):
            concat_audio_chunks([])

    def test_sample_rate_mismatch_raises(self) -> None:
        chunks = [
            AudioChunk(data=b"\x01\x02", sample_rate=24000, channels=1),
            AudioChunk(data=b"\x03\x04", sample_rate=16000, channels=1),
        ]
        with pytest.raises(VoiceBridgeError, match="sample_rate"):
            concat_audio_chunks(chunks)

    def test_channels_mismatch_raises(self) -> None:
        chunks = [
            AudioChunk(data=b"\x01\x02", sample_rate=24000, channels=1),
            AudioChunk(data=b"\x03\x04\x05\x06", sample_rate=24000, channels=2),
        ]
        with pytest.raises(VoiceBridgeError, match="channels"):
            concat_audio_chunks(chunks)
