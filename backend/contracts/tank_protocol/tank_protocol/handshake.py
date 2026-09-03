"""Protocol handshake (plan §5.1 / P1-1).

The server advertises its protocol version and negotiable features on the
``signal: ready`` frame; clients may declare the features they want to
enable with ``{"type": "signal", "content": "capabilities",
"metadata": {"enable": [...]}}``. Both sides treat unknown feature names
as warn-and-ignore (README evolution rule 2), so old clients are
unaffected: their ``ready`` handling already ignores unknown metadata
keys, and they simply never send the declaration.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import __version__

__all__ = ["KNOWN_PROTOCOL_FEATURES", "OPUS_PROFILE", "handshake_metadata"]


# Features a server may advertise / a client may request. The list grows
# additively as phases land: opus (P1-2), config (P1-3), resume (P2).
KNOWN_PROTOCOL_FEATURES: frozenset[str] = frozenset({"opus", "resume", "config"})


# Canonical opus codec parameters (P1-2). The capabilities-ack factory
# embeds these on the wire so clients configure their codecs from the ack
# instead of hardcoding; the server reads them here when building its own
# encoder/decoder. 20ms frames; 32 kbps start; uplink 16 kHz (mic rate),
# downlink 24 kHz (TTS native rate = device speaker rate).
OPUS_PROFILE: dict[str, dict[str, int]] = {
    "uplink": {"sample_rate": 16000, "frame_ms": 20, "bitrate": 32000},
    "downlink": {"sample_rate": 24000, "frame_ms": 20, "bitrate": 32000},
}


def handshake_metadata(features: Iterable[str] = ()) -> dict[str, Any]:
    """The protocol metadata block the server attaches to ``signal: ready``.

    ``protocol_version`` is the ``tank_protocol`` package version — the
    single source of truth. ``protocol_features`` lists the features this
    server actually supports today (empty until P1-2/P1-3 land).
    """
    return {
        "protocol_version": __version__,
        "protocol_features": sorted(set(features)),
    }
