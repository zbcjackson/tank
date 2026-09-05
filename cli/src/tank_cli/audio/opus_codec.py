"""Opus codecs for negotiated connections (protocol plan P1-2, client side).

After the ``signal: capabilities`` ack enables ``opus``, binary audio
switches from raw PCM to one Opus packet per WebSocket message, both
directions. Parameters come from ``tank_protocol.OPUS_PROFILE`` (uplink
16 kHz / downlink 24 kHz mono, 20 ms frames, 32 kbps) — the same constant
the server reads, so both sides configure from one source. This module
implements the client view: encode mic PCM into uplink packets, decode
server packets into playback PCM.

opuslib is soft-imported: if the binding (or libopus) is missing the
client simply never declares ``opus`` and stays on the raw-PCM path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tank_protocol import OPUS_PROFILE

logger = logging.getLogger(__name__)

__all__ = [
    "DOWNLINK_SAMPLE_RATE",
    "OPUS_AVAILABLE",
    "ClientCodecs",
    "OpusDecodeError",
    "OpusDownlinkDecoder",
    "OpusUplinkEncoder",
    "create_client_codecs",
]


def _opuslib_importable() -> bool:
    try:
        import opuslib  # noqa: F401
    except Exception:
        return False
    return True


OPUS_AVAILABLE = _opuslib_importable()

_UPLINK_SAMPLE_RATE = OPUS_PROFILE["uplink"]["sample_rate"]
_UPLINK_FRAME_SAMPLES = _UPLINK_SAMPLE_RATE * OPUS_PROFILE["uplink"]["frame_ms"] // 1000
_UPLINK_BITRATE = OPUS_PROFILE["uplink"]["bitrate"]
DOWNLINK_SAMPLE_RATE = OPUS_PROFILE["downlink"]["sample_rate"]

# libopus decodes at most 120 ms per packet — the buffer capacity we give it.
# Capacity hint, not a duration contract: opus_decode returns the actual
# sample count.
_DOWNLINK_MAX_FRAME_SAMPLES = DOWNLINK_SAMPLE_RATE * 120 // 1000


class OpusDecodeError(Exception):
    """A server downlink packet could not be decoded (dropped by the client)."""


class OpusUplinkEncoder:
    """Encodes 16 kHz mono PCM16 into Opus packets, re-buffering arbitrary
    chunk sizes into the profile's 20 ms frames."""

    def __init__(self) -> None:
        import opuslib

        self._encoder = opuslib.Encoder(
            _UPLINK_SAMPLE_RATE, 1, opuslib.APPLICATION_AUDIO
        )
        self._encoder.bitrate = _UPLINK_BITRATE
        self._buffer = bytearray()

    def feed(self, pcm: bytes) -> list[bytes]:
        """Append PCM and return every complete 20 ms frame as a packet."""
        self._buffer.extend(pcm)
        step = _UPLINK_FRAME_SAMPLES * 2  # int16 → bytes per sample
        packets: list[bytes] = []
        while len(self._buffer) >= step:
            frame = bytes(self._buffer[:step])
            del self._buffer[:step]
            packets.append(self._encoder.encode(frame, _UPLINK_FRAME_SAMPLES))
        return packets


class OpusDownlinkDecoder:
    """Decodes server downlink Opus packets into PCM16 mono at the profile
    rate (24 kHz)."""

    def __init__(self) -> None:
        import opuslib

        self._decoder = opuslib.Decoder(DOWNLINK_SAMPLE_RATE, 1)

    def decode_packet(self, packet: bytes) -> bytes:
        """One wire packet → PCM16 mono bytes. Raises :class:`OpusDecodeError`
        on garbage so the client can drop the packet and keep the connection."""
        import opuslib

        try:
            return self._decoder.decode(packet, _DOWNLINK_MAX_FRAME_SAMPLES)
        except opuslib.OpusError as e:
            raise OpusDecodeError(f"{e} (packet {len(packet)} B)") from e


@dataclass(frozen=True)
class ClientCodecs:
    """Per-connection opus codecs (uplink encode / downlink decode)."""

    uplink: OpusUplinkEncoder
    downlink: OpusDownlinkDecoder


def create_client_codecs() -> ClientCodecs:
    if not OPUS_AVAILABLE:
        raise RuntimeError("opuslib unavailable — opus must never be declared")
    return ClientCodecs(uplink=OpusUplinkEncoder(), downlink=OpusDownlinkDecoder())
