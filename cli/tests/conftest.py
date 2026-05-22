"""Pytest configuration for CLI tests."""

import sys
from unittest.mock import MagicMock

# Try to import sounddevice; if unavailable, provide a mock for test collection.
try:
    import sounddevice  # noqa: F401
except OSError:
    # PortAudio not installed — mock sounddevice so tests can collect.
    # The tests themselves mock specific components, so this just allows collection.
    sys.modules["sounddevice"] = MagicMock()
