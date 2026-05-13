"""Regression test: importing the FastAPI server must not pull in sounddevice.

sounddevice requires the native PortAudio library at import time. The backend
receives audio over WebSocket and never captures from a local microphone, so
no backend code path should drag sounddevice into the import graph. Mic capture
lives in the CLI (tank_cli.audio.input.mic).
"""

from __future__ import annotations

import sys


def test_server_import_does_not_require_sounddevice():
    """Importing tank_backend.api.server must not trigger a sounddevice import."""
    sys.modules.pop("sounddevice", None)

    import tank_backend.api.server  # noqa: F401

    assert "sounddevice" not in sys.modules, (
        "tank_backend.api.server pulled in sounddevice — a native-audio "
        "dependency should not be required to start the backend. Check for a "
        "new eager import chain that reaches tank_backend.audio.input.mic or "
        "similar."
    )
