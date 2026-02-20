# CLI Testing Guidelines

This document provides testing guidelines specific to the Tank CLI/TUI Client.

## Framework

- **Framework**: `pytest` with `pytest-asyncio`
- **TUI Testing**: Textual's built-in `run_test()` pilot
- **Location**: `tests/`

## TDD Workflow

1. Write a failing test describing desired behavior
2. Implement minimal code to pass
3. Refactor while keeping tests green
4. Run full suite before committing

## Testing Commands

```bash
uv run pytest                          # All tests
uv run pytest -v                       # Verbose
uv run pytest tests/test_tui.py        # Specific file
uv run pytest --cov=src/tank_cli       # With coverage
```

## Key Practices

### Mock External Dependencies

Always mock:
- WebSocket connections (`websockets.connect`)
- Audio devices (`sounddevice.InputStream`, `sounddevice.play`)
- Backend server responses

```python
from unittest.mock import AsyncMock, patch

async def test_client_sends_message():
    with patch("websockets.connect") as mock_connect:
        mock_ws = AsyncMock()
        mock_connect.return_value.__aenter__.return_value = mock_ws

        client = WebSocketClient("ws://localhost:8000/ws")
        await client.send_text("hello")

        mock_ws.send.assert_called_once()
```

### TUI Testing with Textual Pilot

```python
from textual.pilot import Pilot
from tank_cli.tui.app import TankApp

async def test_app_displays_message():
    app = TankApp()
    async with app.run_test() as pilot:
        # Simulate receiving a message
        app.post_message(MessageReceived("Hello from assistant"))
        await pilot.pause()

        # Verify it appears in conversation
        conversation = app.query_one("#conversation")
        assert "Hello from assistant" in conversation.renderable
```

### Audio Testing

Generate synthetic audio instead of using real devices:

```python
import numpy as np

def make_audio_frame(sample_rate=16000, duration_ms=20, frequency=440):
    n = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n)
    return (0.3 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
```

### Async Tests

All async tests must be marked or use `asyncio_mode = "auto"` (already configured in `pyproject.toml`):

```python
import pytest

async def test_websocket_reconnect():
    client = WebSocketClient("ws://localhost:8000/ws")
    # Test reconnection logic
    ...
```

## Performance Targets

- Unit tests: < 1 second each
- Full suite: < 30 seconds total
- No real audio devices or network calls in unit tests

## Test Quality Checklist

- [ ] WebSocket and audio devices are mocked
- [ ] Tests verify observable behavior, not internals
- [ ] Async tests run without real I/O
- [ ] TUI tests use Textual pilot
- [ ] Tests complete in < 1 second each
