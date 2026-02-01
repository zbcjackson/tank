# Tank - Voice Assistant

A powerful voice assistant that supports both Chinese and English, capable of answering questions, having conversations, and executing tasks through various tools.

## Features

- 🎤 **Speech Recognition**: Uses OpenAI Whisper for accurate speech-to-text conversion
- 🔊 **Text-to-Speech**: Uses Edge TTS for natural-sounding voice synthesis
- 🧠 **AI Integration**: Powered by LLM via configurable API endpoint
- 🛠️ **Tool Execution**: Built-in tools for calculations, weather, time, and web search
- 🌐 **Web Search**: Real-time web search capability for current information and facts
- 🌏 **Multi-language Support**: Seamless switching between Chinese and English
- ⚙️ **Configurable**: Easy configuration through environment variables
- 🧪 **Tested**: Comprehensive test suite with pytest

## Prerequisites

- Python 3.10 or higher
- An API key from your LLM provider (e.g., OpenRouter, OpenAI, etc.)
- Audio input/output device (microphone and speakers)
- **Optional**: [ffmpeg](https://ffmpeg.org/) on `PATH` — used for TTS MP3 decoding when available (lower latency, fewer audio glitches). Without it, the app falls back to in-process decoding (pydub).

## Installation

1. Clone or download this project
2. Navigate to the project directory
3. Install dependencies with uv:

```bash
uv sync
```

## Configuration

1. Create configuration file:
```bash
python main.py --create-config
```

2. Copy the example configuration:
```bash
cp .env.example .env
```

3. Edit `.env` and add your LLM API key:
```env
LLM_API_KEY=your_api_key_here
```

## Usage

### Basic Usage

Start the voice assistant:
```bash
python main.py
```

### Check System Status

Verify all components are working:
```bash
python main.py --check
```

### Custom Configuration

Use a custom configuration file:
```bash
python main.py --config /path/to/your/.env
```

## Available Tools

The assistant comes with built-in tools:

- **Calculator**: Perform mathematical calculations
- **Weather**: Get weather information (mock data for demo)
- **Time**: Get current date and time
- **Web Search**: Search the internet for current information when the assistant doesn't know the answer

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `LLM_API_KEY` | *required* | Your LLM provider API key |
| `LLM_MODEL` | `anthropic/claude-3-5-nano` | LLM model to use |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API base URL |
| `WHISPER_MODEL_SIZE` | `base` | Whisper model size (tiny/base/small/medium/large) |
| `DEFAULT_LANGUAGE` | `zh` | Default language (auto/en/zh) |
| `AUDIO_DURATION` | `5.0` | Recording duration in seconds |
| `TTS_VOICE_EN` | `en-US-JennyNeural` | English TTS voice |
| `TTS_VOICE_ZH` | `zh-CN-XiaoxiaoNeural` | Chinese TTS voice |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAX_CONVERSATION_HISTORY` | `10` | Max conversation turns to remember |

## LLM Provider Examples

The voice assistant now supports any OpenAI-compatible API. Here are some configuration examples:

### OpenRouter (Default)
```env
LLM_API_KEY=your_openrouter_key
LLM_MODEL=anthropic/claude-3-5-nano
LLM_BASE_URL=https://openrouter.ai/api/v1
```

### OpenAI
```env
LLM_API_KEY=your_openai_key
LLM_MODEL=gpt-4
LLM_BASE_URL=https://api.openai.com/v1
```

### Custom/Self-hosted
```env
LLM_API_KEY=your_custom_key
LLM_MODEL=your-model-name
LLM_BASE_URL=https://your-api-endpoint.com/v1
```

## Development

### Running Tests

```bash
# Run all tests
uv run python -m pytest tests/

# Run with coverage
uv run python -m pytest tests/ --cov=src/voice_assistant

# Run specific test file
uv run python -m pytest tests/test_tools.py
```

### Project Structure

```
tank/
├── src/voice_assistant/
│   ├── audio/              # Speech recognition and TTS
│   ├── llm/               # LLM integration
│   ├── tools/             # Tool execution framework
│   ├── config/            # Configuration management
│   └── assistant.py       # Main assistant class
├── tests/                 # Test suite
├── main.py               # Entry point
└── pyproject.toml        # Project configuration
```

## Usage Examples

### Chinese Conversation (Default)
```
User: "现在几点了？"
Assistant: "现在的时间是2024年1月15日 14时30分25秒"

User: "计算十五乘以八"
Assistant: "15 × 8 = 120"

User: "最新的人工智能发展怎么样？"
Assistant: "让我为您搜索最新的人工智能发展信息... [搜索结果]"
```

### English Conversation
```
User: "What's the time?"
Assistant: "The current time is 2024-01-15 14:30:25"

User: "Calculate 15 times 8"
Assistant: "15 × 8 = 120"

User: "What's the latest news about climate change?"
Assistant: "Let me search for the latest climate change information... [search results]"
```

## Troubleshooting

### Common Issues

1. **No audio input/output**: Ensure your microphone and speakers are working
2. **API errors**: Verify your LLM API key is correct
3. **Dependencies**: Run `uv sync` to install all required packages

### Debug Mode

Enable debug logging:
```env
LOG_LEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

This project is open source and available under the MIT License.