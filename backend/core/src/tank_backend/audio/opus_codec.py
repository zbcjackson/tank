"""Opus codecs for negotiated connections (protocol plan P1-2).

A connection that negotiated the ``opus`` feature (``signal: capabilities``
ack) switches its binary audio frames from raw PCM to Opus packets — one
packet per WebSocket binary message, both directions. Wire parameters come
from ``tank_protocol.OPUS_PROFILE`` (uplink 16 kHz / downlink 24 kHz mono,
20 ms frames, 32 kbps); this module implements the server side: decode
client uplink packets into 16 kHz PCM16 for the pipeline, re-buffer
pipeline output into 24 kHz downlink packets.

opuslib is soft-imported: if the binding (or libopus) is missing, the
server simply does not advertise ``opus`` and every connection stays on
the raw-PCM path.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from tank_protocol import OPUS_PROFILE

logger = logging.getLogger(__name__)

__all__ = [
    "DOWNLINK_SAMPLE_RATE",
    "OPUS_AVAILABLE",
    "OpusDecodeError",
    "OpusDownlinkEncoder",
    "OpusUplinkDecoder",
    "SessionCodecs",
    "create_session_codecs",
    "supported_protocol_features",
    "uplink_sample_rate",
]


def _opuslib_importable() -> bool:
    try:
        import opuslib  # noqa: F401
    except Exception:
        return False
    return True


OPUS_AVAILABLE = _opuslib_importable()

_DOWNLINK_SAMPLE_RATE = OPUS_PROFILE["downlink"]["sample_rate"]
_DOWNLINK_FRAME_SAMPLES = _DOWNLINK_SAMPLE_RATE * OPUS_PROFILE["downlink"]["frame_ms"] // 1000
_DOWNLINK_BITRATE = OPUS_PROFILE["downlink"]["bitrate"]
# Residue older than this is dropped on the next feed: after an interrupt the
# pipeline stops mid-chunk and the tail sits in the buffer; playback faded it
# out, so prepending it to the next response would only add a faint click.
_STALE_RESIDUE_S = 1.0


class OpusDecodeError(Exception):
    """A client uplink packet could not be decoded (dropped by the router)."""


def supported_protocol_features() -> list[str]:
    """Features this server can actually negotiate today."""
    return ["opus"] if OPUS_AVAILABLE else []


def uplink_sample_rate() -> int:
    """PCM rate the opus uplink decodes to (the negotiated profile's)."""
    return OPUS_PROFILE["uplink"]["sample_rate"]


DOWNLINK_SAMPLE_RATE = _DOWNLINK_SAMPLE_RATE

# libopus decodes at most 120 ms per packet — the buffer capacity we give it.
_UPLINK_MAX_FRAME_SAMPLES = (
    OPUS_PROFILE["uplink"]["sample_rate"] * 120 // 1000
)


class OpusUplinkDecoder:
    """Decodes client uplink Opus packets (profile rate, mono) into PCM16."""

    def __init__(self) -> None:
        import opuslib

        self._decoder = opuslib.Decoder(OPUS_PROFILE["uplink"]["sample_rate"], 1)

    def decode_packet(self, packet: bytes) -> bytes:
        """One wire packet → PCM16 mono bytes. Raises :class:`OpusDecodeError`
        on garbage so the router can drop the frame and keep the connection."""
        import opuslib

        try:
            # Capacity hint, not a duration contract: some encoders (e.g.
            # Chrome's WebCodecs opus) emit variable-duration packets, so
            # allow libopus's 120 ms maximum instead of exactly one 20 ms
            # frame — opus_decode returns the actual sample count.
            return self._decoder.decode(packet, _UPLINK_MAX_FRAME_SAMPLES)
        except opuslib.OpusError as e:
            raise OpusDecodeError(f"{e} (packet {len(packet)} B)") from e


class OpusDownlinkEncoder:
    """Encodes profile-rate mono PCM16 into Opus packets, re-buffering
    arbitrary chunk sizes into the profile's 20 ms frames. A residue older
    than :data:`_STALE_RESIDUE_S` is dropped on the next feed (interrupt gap).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        import opuslib

        self._encoder = opuslib.Encoder(
            _DOWNLINK_SAMPLE_RATE, 1, opuslib.APPLICATION_AUDIO
        )
        self._encoder.bitrate = _DOWNLINK_BITRATE
        self._buffer = bytearray()
        self._clock = clock
        self._last_feed = clock()

    def feed(self, pcm: bytes) -> list[bytes]:
        """Append PCM and return every complete 20 ms frame as a packet."""
        now = self._clock()
        if now - self._last_feed > _STALE_RESIDUE_S:
            self._buffer.clear()
        self._last_feed = now

        self._buffer.extend(pcm)
        step = _DOWNLINK_FRAME_SAMPLES * 2  # int16 → bytes per sample
        packets: list[bytes] = []
        while len(self._buffer) >= step:
            frame = bytes(self._buffer[:step])
            del self._buffer[:step]
            packets.append(self._encoder.encode(frame, _DOWNLINK_FRAME_SAMPLES))
        return packets


@dataclass(frozen=True)
class SessionCodecs:
    """Per-connection opus codecs (uplink decode / downlink encode)."""

    uplink: OpusUplinkDecoder
    downlink: OpusDownlinkEncoder


def create_session_codecs() -> SessionCodecs:
    if not OPUS_AVAILABLE:
        raise RuntimeError("opuslib unavailable — opus was never advertised")
    return SessionCodecs(uplink=OpusUplinkDecoder(), downlink=OpusDownlinkEncoder())
