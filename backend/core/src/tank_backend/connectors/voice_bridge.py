"""Audio format bridge for connectors.

Turns platform-native voice payloads (Telegram's Ogg/Opus, probably the
same for Slack and Feishu when their connectors arrive) into Tank's
internal PCM representation and back. Pure utility functions with no
dependency on Tank internals beyond :class:`AudioChunk` — connectors
import them directly, no orchestration state.

Runs on pydub, which shells out to ffmpeg for all real work. ffmpeg
must be on ``PATH``; the module raises a descriptive error at first use
if it isn't.

Every function here is blocking. Callers that care about the event
loop must wrap calls in :func:`asyncio.to_thread`.
"""

from __future__ import annotations

import io
import logging
import shutil
from typing import TYPE_CHECKING

import numpy as np
from pydub import AudioSegment

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tank_contracts.tts import AudioChunk

logger = logging.getLogger(__name__)


# Tank's ASR engines (sherpa-onnx, funasr, elevenlabs) all expect
# float32 mono at 16 kHz. Keep that as the canonical in-process format.
_ASR_SAMPLE_RATE = 16000
_ASR_CHANNELS = 1


class VoiceBridgeError(RuntimeError):
    """Raised when audio conversion fails in a way the caller can surface
    to the user (e.g. "sorry, I couldn't read that voice message")."""


def _ensure_ffmpeg_available() -> None:
    """Raise a clear error early if ffmpeg isn't installed.

    pydub's default failure mode is an obscure ``FileNotFoundError`` deep
    in its subprocess code. Catch it once with a useful message so
    operators know what to install.
    """
    if shutil.which("ffmpeg") is None:
        raise VoiceBridgeError(
            "ffmpeg not found on PATH. Install ffmpeg to enable voice "
            "support (e.g. `brew install ffmpeg` on macOS, "
            "`apt install ffmpeg` on Debian/Ubuntu)."
        )


# ---------------------------------------------------------------------------
# Inbound: Ogg/Opus → 16 kHz float32 PCM
# ---------------------------------------------------------------------------


def decode_ogg_opus(data: bytes) -> np.ndarray:
    """Decode Telegram-style voice bytes to ASR-ready float32 PCM.

    Telegram voice notes are always Ogg-encapsulated Opus at 48 kHz mono.
    We resample to 16 kHz mono and normalize int16 to float32 in
    ``[-1.0, 1.0]`` — the format every ASR engine in the plugin tree
    expects.

    Returns a 1-D ``np.ndarray`` of dtype ``float32``.
    """
    if not data:
        raise VoiceBridgeError("voice decode: empty payload")
    _ensure_ffmpeg_available()

    try:
        seg = AudioSegment.from_file(io.BytesIO(data), format="ogg")
    except Exception as exc:
        raise VoiceBridgeError(
            f"voice decode failed (ffmpeg could not parse the payload): {exc}"
        ) from exc

    return _segment_to_float32_pcm(seg)


# Mapping from MIME type to pydub's ``format=`` hint. pydub/ffmpeg can
# usually sniff the format from the magic bytes, but the hint resolves
# a few real-world ambiguities — notably mp4 vs m4a, which share a
# container. Keys cover the audio types Slack, Discord, and generic
# webhook sources are likely to deliver; unknown MIMEs fall through to
# sniffing (``None``).
_MIME_TO_FORMAT_HINT: dict[str, str] = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}


def decode_any_audio(data: bytes, *, mime_type: str | None = None) -> np.ndarray:
    """Decode arbitrary audio bytes to ASR-ready float32 PCM.

    Format-agnostic sibling of :func:`decode_ogg_opus`. Used by
    connectors (Slack, and any future multi-format platform) that
    deliver audio in formats other than Telegram's fixed Ogg/Opus —
    WebM (Slack/Discord desktop), M4A (Apple mobile), MP3 (legacy), etc.

    ``mime_type`` is an optional hint passed to ffmpeg as the
    ``format=`` argument when we have a reliable mapping. When the
    MIME is unknown (or ``None``), pydub/ffmpeg sniff the magic bytes
    — which works for all the formats in :data:`_MIME_TO_FORMAT_HINT`
    too, but explicit hints are faster and rule out edge-case
    misdetections.

    Returns a 1-D ``np.ndarray`` of dtype ``float32`` at 16 kHz mono.
    Raises :class:`VoiceBridgeError` on empty input or decode failure.
    """
    if not data:
        raise VoiceBridgeError("voice decode: empty payload")
    _ensure_ffmpeg_available()

    # Normalise ``audio/ogg; codecs=opus`` → ``audio/ogg`` before lookup.
    normalised = (mime_type or "").split(";", 1)[0].strip().lower()
    format_hint = _MIME_TO_FORMAT_HINT.get(normalised)

    try:
        seg = AudioSegment.from_file(io.BytesIO(data), format=format_hint)
    except Exception as exc:
        raise VoiceBridgeError(
            f"voice decode failed (ffmpeg could not parse the payload, "
            f"mime={mime_type!r}, hint={format_hint!r}): {exc}"
        ) from exc

    return _segment_to_float32_pcm(seg)


def _segment_to_float32_pcm(seg: AudioSegment) -> np.ndarray:
    """Convert an :class:`AudioSegment` to 16 kHz mono float32 PCM.

    Shared post-decode step for both :func:`decode_ogg_opus` and
    :func:`decode_any_audio` — resampling + mono downmix + normalise.
    Keeping the conversion in one place means a future change (e.g.
    bumping the ASR sample rate) flows to every connector at once.
    """
    seg = seg.set_channels(_ASR_CHANNELS).set_frame_rate(_ASR_SAMPLE_RATE)
    if seg.sample_width != 2:
        # Force 16-bit PCM so the int16→float32 step is unambiguous.
        seg = seg.set_sample_width(2)

    # pydub's stub types ``raw_data`` as optional (covers the rare edge
    # case of an uninitialised segment). In practice every post-decode
    # segment has bytes; assert so the narrow lands.
    raw = seg.raw_data
    assert raw is not None, "AudioSegment.raw_data unexpectedly None after decode"  # noqa: S101
    samples = np.frombuffer(raw, dtype=np.int16)
    if samples.size == 0:
        raise VoiceBridgeError("voice decode: produced no samples")

    return (samples.astype(np.float32) / 32768.0).copy()


# ---------------------------------------------------------------------------
# Outbound: PCM → Ogg/Opus
# ---------------------------------------------------------------------------


def encode_pcm_to_opus(pcm: bytes, sample_rate: int, *, channels: int = 1) -> bytes:
    """Encode int16 PCM bytes to Ogg-encapsulated Opus.

    Telegram's ``send_voice`` requires Ogg/Opus. pydub → ffmpeg → libopus
    handles resampling if ``sample_rate`` doesn't match one of Opus's
    native rates (8/16/24/48 kHz — ffmpeg resamples automatically).

    ``pcm`` must be little-endian int16 bytes.
    """
    if not pcm:
        raise VoiceBridgeError("voice encode: empty PCM payload")
    if sample_rate <= 0:
        raise VoiceBridgeError(f"voice encode: invalid sample_rate {sample_rate}")
    _ensure_ffmpeg_available()

    seg = AudioSegment(
        data=pcm,
        sample_width=2,
        frame_rate=sample_rate,
        channels=channels,
    )

    out = io.BytesIO()
    try:
        seg.export(out, format="ogg", codec="libopus")
    except Exception as exc:
        raise VoiceBridgeError(f"voice encode failed: {exc}") from exc

    result = out.getvalue()
    if not result:
        raise VoiceBridgeError("voice encode: ffmpeg produced no output")
    return result


# ---------------------------------------------------------------------------
# AudioChunk concatenation
# ---------------------------------------------------------------------------


def concat_audio_chunks(
    chunks: Sequence[AudioChunk],
) -> tuple[bytes, int]:
    """Concatenate TTS :class:`AudioChunk` s into a single PCM stream.

    Returns ``(pcm_int16_bytes, sample_rate)`` ready to feed into
    :func:`encode_pcm_to_opus`. All chunks must share the same sample
    rate and channel layout — if a future engine emits mixed rates we
    can resample here, but Tank's current engines (edge, cosyvoice, etc.)
    are all fixed-rate.

    Empty input raises :class:`VoiceBridgeError` — callers should check
    ``len(chunks)`` before calling so they can fail fast without burning
    an encode call.
    """
    if not chunks:
        raise VoiceBridgeError("concat: no chunks to concatenate")

    first = chunks[0]
    target_sr = first.sample_rate
    target_channels = first.channels

    for idx, chunk in enumerate(chunks):
        if chunk.sample_rate != target_sr:
            raise VoiceBridgeError(
                f"concat: chunk {idx} sample_rate {chunk.sample_rate} "
                f"!= first {target_sr}; mixed-rate TTS output is not supported yet",
            )
        if chunk.channels != target_channels:
            raise VoiceBridgeError(
                f"concat: chunk {idx} channels {chunk.channels} "
                f"!= first {target_channels}",
            )

    return b"".join(c.data for c in chunks), target_sr


__all__ = [
    "VoiceBridgeError",
    "concat_audio_chunks",
    "decode_ogg_opus",
    "encode_pcm_to_opus",
]
