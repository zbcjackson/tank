# Tank Backend

Backend API server for the Tank Voice Assistant.

## Features

- FastAPI-based WebSocket server
- Speech recognition (ASR) with Faster Whisper
- Text-to-Speech (TTS) with Edge TTS
- LLM integration (OpenAI, Gemini)
- Tool calling support
- Real-time audio streaming

## Installation

```bash
cd backend
uv sync
```

## Usage

```bash
# Start the server
uv run tank-backend

# With custom host/port
uv run tank-backend --host 0.0.0.0 --port 8000

# Create example config
uv run tank-backend --create-config
```

## Development

```bash
# Run tests
uv run pytest

# Run with dev dependencies
uv sync --group dev
```

## Configuration

Copy `.env.example` to `.env` and configure:

- `OPENAI_API_KEY` - OpenAI API key
- `GEMINI_API_KEY` - Google Gemini API key
- Other settings as needed

## API

WebSocket endpoint: `ws://localhost:8000/ws/{session_id}`

See `tank_backend/api/schemas.py` for message formats.
