# CLI Development Guide

This document provides development commands and workflows for the Tank CLI/TUI Client.

## Prerequisites

- Python 3.10+
- uv (package manager)
- Audio device (microphone + speaker)
- Tank Backend running (see `../backend/DEVELOPMENT.md`)

## Setup

```bash
cd cli

# Install dependencies
uv sync

# Install dev dependencies
uv sync --group dev
```

## Running the CLI

```bash
# Connect to default backend (localhost:8000)
uv run tank

# Connect to custom server
uv run tank --server 192.168.1.100:8000

# Use custom config
uv run tank --config /path/to/.env

# Check system status
uv run tank --check
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/tank_cli --cov-report=html

# Run specific test file
uv run pytest tests/test_tui.py

# Run with verbose output
uv run pytest -v
```

## TUI Development

```bash
# Launch Textual dev console (live reload + inspector)
uv run textual console

# Run app with dev console attached
uv run textual run --dev src/tank_cli/tui/app.py

# Show widget tree
uv run textual run --dev src/tank_cli/tui/app.py --screenshot
```

## Common Tasks

### Add a New UI Widget

1. Create widget file in `src/tank_cli/tui/ui/`
2. Inherit from appropriate Textual widget
3. Add CSS in `src/tank_cli/tui/app.tcss`
4. Compose into app layout
5. Write tests

### Add a New Configuration Option

1. Add field to `CLIConfig` in `src/tank_cli/config/settings.py`
2. Document in this file
3. Update `.env.example` if needed

## Troubleshooting

### Audio Device Issues

```bash
python -c "import sounddevice; print(sounddevice.query_devices())"
```

### WebSocket Connection Issues

```bash
# Test backend is running
curl http://localhost:8000/health

# Test WebSocket manually
npx wscat -c ws://localhost:8000/ws
```

### TUI Rendering Issues

```bash
# Run with Textual dev console for live inspection
uv run textual console
```
