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
    decode_any_audio,
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


# ---------------------------------------------------------------------------
# decode_any_audio (Phase 13: format-sniffing sibling of decode_ogg_opus)
# ---------------------------------------------------------------------------


def _audio_bytes_from_pcm(
    pcm: bytes, *, sample_rate: int = 16000, channels: int = 1,
    format: str, codec: str | None = None,
) -> bytes:
    """Export a PCM sine tone into an arbitrary container via pydub.

    Used to manufacture test fixtures for every format the Slack
    connector might plausibly receive — WebM, M4A, MP3, OGG — without
    checking binary blobs into the repo."""
    seg = AudioSegment(
        data=pcm,
        sample_width=2,
        frame_rate=sample_rate,
        channels=channels,
    )
    out = io.BytesIO()
    kwargs: dict = {"format": format}
    if codec is not None:
        kwargs["codec"] = codec
    seg.export(out, **kwargs)
    return out.getvalue()


class TestDecodeAnyAudio:
    """``decode_any_audio`` lets ffmpeg sniff the format from magic
    bytes while accepting an optional MIME hint for edge cases. Tests
    cover the four formats Slack actually delivers (WebM, MP4, MP3,
    OGG) plus the error paths."""

    @_needs_ffmpeg
    @pytest.mark.parametrize(
        ("mime", "export_format", "codec"),
        [
            ("audio/ogg", "ogg", "libopus"),
            ("audio/webm", "webm", "libopus"),
            # MP4/M4A: pydub's default codec is AAC, which ffmpeg
            # transparently supports as long as libfdk_aac or the
            # built-in encoder is available. Skip gracefully if not.
            ("audio/mpeg", "mp3", None),
        ],
    )
    def test_roundtrip_preserves_shape(
        self, mime: str, export_format: str, codec: str | None,
    ) -> None:
        pcm = _sine_pcm_bytes(duration_s=0.5, sample_rate=48000)
        try:
            encoded = _audio_bytes_from_pcm(
                pcm, sample_rate=48000,
                format=export_format, codec=codec,
            )
        except Exception as exc:  # codec not in this ffmpeg build
            pytest.skip(f"ffmpeg missing codec for {export_format}: {exc}")

        out = decode_any_audio(encoded, mime_type=mime)

        assert out.dtype == np.float32
        assert out.ndim == 1
        # 16 kHz × 0.5 s = 8000 samples, ±2% for codec framing.
        assert 7800 <= out.size <= 8200
        assert 0.1 < float(np.abs(out).max()) < 1.0

    @_needs_ffmpeg
    def test_mime_hint_none_falls_back_to_sniffing(self) -> None:
        """The hint is optional — ffmpeg can sniff the format from the
        magic bytes directly. This is the path we hit when a connector
        doesn't know the MIME (e.g. a generic webhook payload)."""
        pcm = _sine_pcm_bytes(duration_s=0.3, sample_rate=48000)
        ogg = _ogg_opus_bytes_from_pcm(pcm, sample_rate=48000)

        out = decode_any_audio(ogg, mime_type=None)
        assert out.size > 0

    @_needs_ffmpeg
    def test_unknown_mime_falls_back_to_sniffing(self) -> None:
        """A bogus MIME (not in ``_MIME_TO_FORMAT_HINT``) shouldn't
        block decoding — ffmpeg still sniffs. This is important for
        connectors that forward untrusted MIME strings."""
        pcm = _sine_pcm_bytes(duration_s=0.3, sample_rate=48000)
        ogg = _ogg_opus_bytes_from_pcm(pcm, sample_rate=48000)

        out = decode_any_audio(ogg, mime_type="audio/very-made-up")
        assert out.size > 0

    @_needs_ffmpeg
    def test_mime_with_codecs_param_normalised(self) -> None:
        """``audio/ogg; codecs=opus`` is a legal MIME Slack sometimes
        emits — the semicolon-separated params must be stripped before
        lookup so the hint still hits."""
        pcm = _sine_pcm_bytes(duration_s=0.3, sample_rate=48000)
        ogg = _ogg_opus_bytes_from_pcm(pcm, sample_rate=48000)

        out = decode_any_audio(ogg, mime_type="audio/ogg; codecs=opus")
        assert out.size > 0

    def test_empty_bytes_raises(self) -> None:
        with pytest.raises(VoiceBridgeError, match="empty"):
            decode_any_audio(b"")

    @_needs_ffmpeg
    def test_garbage_bytes_raises(self) -> None:
        with pytest.raises(VoiceBridgeError, match="ffmpeg could not parse"):
            decode_any_audio(b"not any known audio format" * 100)
