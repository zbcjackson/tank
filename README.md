# Tank - Voice Assistant

A powerful voice assistant that supports both Chinese and English, capable of answering questions, having conversations, and executing tasks through various tools.

## Architecture

This is a monorepo containing three projects:

- **`backend/`** - FastAPI-based backend server (Python)
  - Speech recognition (ASR)
  - Text-to-Speech (TTS)
  - LLM integration
  - Tool execution

- **`cli/`** - CLI/TUI client (Python)
  - Textual-based terminal interface
  - Local audio capture and playback
  - WebSocket client

- **`web/`** - Web frontend (TypeScript/React)
  - Browser-based interface
  - WebRTC audio streaming
  - Modern UI

## Quick Start

### 1. Start the Backend

```bash
cd backend
uv sync
uv run tank-backend --create-config  # Create .env.example
cp .env.example .env                  # Edit with your API keys
uv run tank-backend                   # Start server on :8000
```

### 2. Start a Client

**Option A: CLI/TUI Client**
```bash
cd cli
uv sync
uv run tank                           # Connects to localhost:8000
```

**Option B: Web Client**
```bash
cd web
pnpm install
pnpm dev                              # Opens browser
```

## Features

- 🎤 **Speech Recognition**: OpenAI Whisper for accurate speech-to-text
- 🔊 **Text-to-Speech**: Edge TTS for natural voice synthesis
- 🧠 **AI Integration**: Powered by LLM (OpenAI, Gemini, etc.)
- 🛠️ **Tool Execution**: Calculator, weather, time, web search
- 🌐 **Web Search**: Real-time information retrieval
- 🌏 **Multi-language**: Seamless Chinese/English switching
- ⚙️ **Configurable**: Environment-based configuration
- 🧪 **Tested**: Comprehensive test coverage

## Prerequisites

- Python 3.10+ (for backend and CLI)
- Node.js 18+ (for web frontend)
- Audio input/output device
- LLM API key (OpenAI, OpenRouter, etc.)
- **Optional**: [ffmpeg](https://ffmpeg.org/) for better TTS performance

## Configuration

### Backend Configuration

Edit `backend/.env`:

```env
LLM_API_KEY=your_api_key_here
LLM_MODEL=anthropic/claude-3-5-nano
LLM_BASE_URL=https://openrouter.ai/api/v1
WHISPER_MODEL_SIZE=base
DEFAULT_LANGUAGE=zh
TTS_VOICE_EN=en-US-JennyNeural
TTS_VOICE_ZH=zh-CN-XiaoxiaoNeural
```

See `backend/README.md` for full configuration options.

## Development

### Backend Development

```bash
cd backend
uv sync --group dev
uv run pytest                         # Run tests
```

### CLI Development

```bash
cd cli
uv sync --group dev
uv run pytest                         # Run tests
uv run textual console                # Debug TUI
```

### Web Development

```bash
cd web
pnpm install
pnpm dev                              # Dev server
pnpm build                            # Production build
```

## Project Structure

```
tank/
├── backend/                # Backend API server
│   ├── src/tank_backend/
│   │   ├── api/           # FastAPI routes
│   │   ├── audio/         # ASR & TTS
│   │   ├── core/          # Brain & Assistant
│   │   ├── llm/           # LLM integration
│   │   └── tools/         # Tool execution
│   ├── tests/
│   └── pyproject.toml
├── cli/                   # CLI/TUI client
│   ├── src/tank_cli/
│   │   ├── cli/           # WebSocket client
│   │   ├── tui/           # Textual UI
│   │   └── config/        # Configuration
│   ├── tests/
│   └── pyproject.toml
├── web/                   # Web frontend
│   ├── src/
│   ├── public/
│   └── package.json
└── README.md             # This file
```

## Available Tools

- **Calculator**: Mathematical calculations
- **Weather**: Weather information
- **Time**: Current date and time
- **Web Search**: Internet search for current information

## Usage Examples

### Chinese Conversation
```
User: "现在几点了？"
Assistant: "现在的时间是2024年1月15日 14时30分25秒"

User: "计算十五乘以八"
Assistant: "15 × 8 = 120"
```

### English Conversation
```
User: "What's the time?"
Assistant: "The current time is 2024-01-15 14:30:25"

User: "Calculate 15 times 8"
Assistant: "15 × 8 = 120"
```

## Troubleshooting

### Backend Issues
- Verify API keys in `backend/.env`
- Check logs: `LOG_LEVEL=DEBUG`
- Ensure port 8000 is available

### CLI Issues
- Verify backend is running
- Check audio device permissions
- Test connection: `uv run tank --server localhost:8000`

### Web Issues
- Check browser console for errors
- Verify WebSocket connection
- Ensure microphone permissions granted

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

This project is open source and available under the MIT License.
