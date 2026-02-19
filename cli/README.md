# Tank CLI

CLI/TUI client for the Tank Voice Assistant.

## Features

- Textual-based TUI interface
- WebSocket client connecting to backend
- Local audio capture (microphone)
- Local audio playback (speakers)
- Voice activity detection (VAD)

## Installation

```bash
cd cli
uv sync
```

## Usage

```bash
# Start the TUI (connects to localhost:8000 by default)
uv run tank

# Connect to custom server
uv run tank --server example.com:8000

# Create example config
uv run tank --create-config
```

## Development

```bash
# Run tests
uv run pytest

# Run with dev dependencies
uv sync --group dev

# Run with Textual dev tools
uv run textual console
```

## Configuration

The CLI uses minimal configuration. Audio settings are handled locally.

## Architecture

The CLI is a thin client that:
1. Captures audio from the microphone
2. Sends audio/text to the backend via WebSocket
3. Receives responses and audio from the backend
4. Plays audio locally through speakers

All AI processing (ASR, LLM, TTS) happens on the backend.
