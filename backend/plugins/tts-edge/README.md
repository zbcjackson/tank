# Edge TTS Plugin

Microsoft Edge TTS plugin for Tank Voice Assistant.

## Overview

This plugin provides Text-to-Speech functionality using Microsoft Edge's neural TTS service. It implements the `TTSEngine` interface from `tank_contracts.tts` and integrates seamlessly with the Tank backend.

## Features

- **Streaming TTS generation** - Low latency audio streaming
- **100+ voices** - Multiple languages and voice styles
- **MP3 → PCM decoding** - Via ffmpeg (preferred) or pydub (fallback)
- **Interruptible generation** - Can be cancelled mid-stream
- **Automatic voice selection** - Based on language (en/zh)
- **High quality** - Neural voices with natural prosody

## Installation

This plugin is installed automatically as part of the Tank backend workspace:

```bash
cd backend
uv sync
```

The plugin is registered in `backend/pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "core",
    "contracts",
    "plugins/tts-edge",
]
```

## Configuration

Configure in `backend/core/config.yaml`:

```yaml
tts:
  plugin: tts-edge           # Plugin folder name
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
```

### Available Configuration Options

- **voice_en** - Voice for English text (default: `en-US-JennyNeural`)
- **voice_zh** - Voice for Chinese text (default: `zh-CN-XiaoxiaoNeural`)

## Dependencies

- **edge-tts>=6.1.0** - Microsoft Edge TTS client
- **pydub>=0.25.0** - Audio processing (MP3 decoding fallback)
- **ffmpeg** (optional, recommended) - Fast MP3 decoding

### Installing ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## Usage

The plugin is loaded automatically by the backend. No manual initialization required.

### Programmatic Usage

```python
from tts_edge import create_engine

# Create engine instance
config = {
    "voice_en": "en-US-JennyNeural",
    "voice_zh": "zh-CN-XiaoxiaoNeural"
}
engine = create_engine(config)

# Generate audio stream
async for chunk in engine.generate_stream("Hello world", language="en"):
    # chunk is an AudioChunk with PCM data
    print(f"Received {len(chunk.data)} bytes at {chunk.sample_rate} Hz")
```

## Architecture

### Class Structure

```
EdgeTTSEngine (implements TTSEngine)
├── __init__(config)
├── generate_stream(text, language, **kwargs) → AsyncIterator[AudioChunk]
└── _decode_mp3_to_pcm(mp3_data) → bytes
```

### Data Flow

```
Text → Edge TTS API → MP3 chunks → Decoder → PCM chunks → AudioChunk
```

### Decoding Strategy

1. **Try ffmpeg** (fast, efficient)
   - Uses `ffmpeg` command-line tool
   - Converts MP3 → PCM in one pass
   - Preferred method

2. **Fallback to pydub** (slower, pure Python)
   - Uses pydub library
   - Converts MP3 → PCM in memory
   - Works without ffmpeg installed

## Testing

```bash
# Run plugin tests
cd backend/plugins/tts-edge
uv run pytest

# Run with coverage
uv run pytest --cov=tts_edge --cov-report=html

# Run specific test
uv run pytest tests/test_engine.py::test_generate_stream
```

Test coverage: 4/4 tests passing ✅

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
└── test_engine.py        # Engine tests
    ├── test_create_engine
    ├── test_generate_stream
    ├── test_decode_mp3_ffmpeg
    └── test_decode_mp3_pydub
```

## Available Voices

See [Microsoft Edge TTS Voice Gallery](https://speech.microsoft.com/portal/voicegallery) for the complete list.

### Popular English Voices

- **en-US-JennyNeural** - Female, friendly (default)
- **en-US-GuyNeural** - Male, professional
- **en-US-AriaNeural** - Female, expressive
- **en-GB-SoniaNeural** - Female, British
- **en-AU-NatashaNeural** - Female, Australian

### Popular Chinese Voices

- **zh-CN-XiaoxiaoNeural** - Female, standard Mandarin (default)
- **zh-CN-YunxiNeural** - Male, standard Mandarin
- **zh-CN-XiaoyiNeural** - Female, warm
- **zh-TW-HsiaoChenNeural** - Female, Taiwanese Mandarin
- **zh-HK-HiuGaaiNeural** - Female, Cantonese

## Performance

- **Latency**: ~200-500ms for first chunk
- **Throughput**: Streams audio as it's generated
- **Memory**: Low memory footprint (streaming)
- **CPU**: Minimal (decoding only)

## Troubleshooting

### No audio output

1. Check ffmpeg installation: `which ffmpeg`
2. Check pydub installation: `uv pip list | grep pydub`
3. Check plugin configuration in `core/config.yaml`

### Slow generation

1. Install ffmpeg for faster decoding
2. Check network connection to Edge TTS service
3. Reduce text length for faster response

### Voice not found

1. Verify voice name in [Voice Gallery](https://speech.microsoft.com/portal/voicegallery)
2. Check spelling in `core/config.yaml`
3. Ensure voice supports the target language

## Development

### Adding a New Voice

1. Find voice name in [Voice Gallery](https://speech.microsoft.com/portal/voicegallery)
2. Update `core/config.yaml`:
   ```yaml
   tts:
     plugin: tts-edge
     config:
       voice_en: en-US-AriaNeural  # New voice
       voice_zh: zh-CN-XiaoxiaoNeural
   ```
3. Restart backend

### Extending the Plugin

To add new features:

1. Modify `tts_edge/engine.py`
2. Add tests in `tests/test_engine.py`
3. Update this README
4. Run tests: `uv run pytest`

## API Reference

### `create_engine(config: dict) -> EdgeTTSEngine`

Factory function to create engine instance.

**Parameters:**
- `config` - Configuration dictionary with `voice_en` and `voice_zh`

**Returns:**
- `EdgeTTSEngine` instance

### `EdgeTTSEngine.generate_stream(text: str, language: str = "en", **kwargs) -> AsyncIterator[AudioChunk]`

Generate audio stream from text.

**Parameters:**
- `text` - Text to synthesize
- `language` - Language code (`en` or `zh`)
- `**kwargs` - Additional parameters (unused)

**Yields:**
- `AudioChunk` - Audio data chunks (PCM, 24 kHz, mono)

**Raises:**
- `RuntimeError` - If TTS generation fails

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run tests: `uv run pytest`
6. Submit a pull request

## Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/tank/issues)
- **Documentation**: [Tank Backend Docs](../../README.md)
- **Edge TTS Docs**: [edge-tts on PyPI](https://pypi.org/project/edge-tts/)

---

**Plugin**: `tts-edge`
**Version**: 1.0.0
**Implements**: `TTSEngine` from `tank-contracts`
**Status**: ✅ Production ready
