# Tank Plugins

Pluggable components for the Tank Voice Assistant backend.

## Overview

The Tank backend uses a plugin architecture to support different TTS (Text-to-Speech) engines. Plugins are dynamically loaded at runtime based on configuration, allowing easy extension without modifying core code.

## Architecture

```
backend/
├── core/                    # Core application
│   └── src/tank_backend/
│       └── plugin/         # Plugin loader
├── contracts/              # Shared interfaces
│   └── tank_contracts/
│       └── tts.py         # TTSEngine ABC
└── plugins/                # Plugin implementations
    ├── plugins.yaml        # Configuration
    ├── tts-edge/          # Edge TTS plugin
    └── tts-cosyvoice/     # CosyVoice TTS plugin
```

### How It Works

1. **Configuration** - `plugins.yaml` specifies which plugin to use
2. **Loading** - Core application loads plugin module dynamically
3. **Instantiation** - Calls plugin's `create_engine(config)` factory function
4. **Usage** - Core uses plugin via `TTSEngine` interface

## Plugin Configuration

Edit `plugins/plugins.yaml` to configure active plugins:

```yaml
tts:
  plugin: tts-edge           # Plugin folder name under plugins/
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
```

### Configuration Structure

```yaml
<slot>:                      # Plugin slot (tts, asr, llm, etc.)
  plugin: <plugin-name>      # Plugin folder name
  config:                    # Plugin-specific configuration
    <key>: <value>
```

## Available Plugins

### TTS Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| **tts-edge** | Microsoft Edge TTS | ✅ Production |
| **tts-cosyvoice** | CosyVoice TTS (requires server) | ✅ Production |
| tts-vits | VITS TTS | 🚧 Planned |

## Creating a Plugin

### 1. Plugin Structure

Create a new directory under `plugins/`:

```
plugins/
└── tts-myplugin/
    ├── tts_myplugin/
    │   ├── __init__.py
    │   └── engine.py
    ├── tests/
    │   └── test_engine.py
    ├── pyproject.toml
    └── README.md
```

### 2. Implement TTSEngine

Create `tts_myplugin/engine.py`:

```python
from tank_contracts.tts import TTSEngine, AudioChunk
from typing import AsyncIterator

class MyTTSEngine(TTSEngine):
    """Custom TTS engine implementation."""

    def __init__(self, config: dict):
        """
        Initialize TTS engine.

        Args:
            config: Configuration from plugins.yaml
        """
        self.config = config
        # Initialize your TTS engine here

    async def generate_stream(
        self,
        text: str,
        language: str = "en",
        **kwargs
    ) -> AsyncIterator[AudioChunk]:
        """
        Generate audio stream from text.

        Args:
            text: Text to synthesize
            language: Language code (en, zh, etc.)
            **kwargs: Additional parameters

        Yields:
            AudioChunk: Audio data chunks
        """
        # Your TTS implementation
        audio_data = await self._synthesize(text, language)

        # Yield audio chunks
        yield AudioChunk(
            data=audio_data,
            sample_rate=24000,
            channels=1,
            format="pcm_s16le"
        )

    async def _synthesize(self, text: str, language: str) -> bytes:
        """Synthesize text to audio."""
        # Your synthesis logic
        pass
```

### 3. Export Factory Function

Create `tts_myplugin/__init__.py`:

```python
from .engine import MyTTSEngine

def create_engine(config: dict) -> MyTTSEngine:
    """
    Factory function called by plugin loader.

    Args:
        config: Configuration from plugins.yaml

    Returns:
        MyTTSEngine instance
    """
    return MyTTSEngine(config)

__all__ = ["create_engine", "MyTTSEngine"]
```

### 4. Define Dependencies

Create `pyproject.toml`:

```toml
[project]
name = "tts-myplugin"
version = "1.0.0"
description = "My TTS plugin for Tank"
requires-python = ">=3.10"
dependencies = [
    "tank-contracts",
    # Your plugin dependencies
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 5. Add Tests

Create `tests/test_engine.py`:

```python
import pytest
from tts_myplugin import create_engine
from tank_contracts.tts import AudioChunk

@pytest.mark.asyncio
async def test_create_engine():
    """Test engine creation."""
    config = {"param": "value"}
    engine = create_engine(config)
    assert engine is not None

@pytest.mark.asyncio
async def test_generate_stream():
    """Test audio generation."""
    engine = create_engine({})
    chunks = []

    async for chunk in engine.generate_stream("Hello", language="en"):
        assert isinstance(chunk, AudioChunk)
        assert chunk.sample_rate > 0
        assert len(chunk.data) > 0
        chunks.append(chunk)

    assert len(chunks) > 0
```

### 6. Register in Workspace

Add to `backend/pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "core",
    "contracts",
    "plugins/tts-edge",
    "plugins/tts-myplugin",  # Add your plugin
]
```

### 7. Configure Plugin

Update `plugins/plugins.yaml`:

```yaml
tts:
  plugin: tts-myplugin
  config:
    param: value
```

### 8. Install and Test

```bash
# Install plugin
cd backend
uv sync

# Run tests
cd plugins/tts-myplugin
uv run pytest

# Test with backend
cd ../../core
uv run tank-backend
```

## Plugin Interface

### TTSEngine (Required)

All TTS plugins must implement `TTSEngine` from `tank_contracts.tts`:

```python
class TTSEngine(ABC):
    """Abstract base class for TTS engines."""

    @abstractmethod
    async def generate_stream(
        self,
        text: str,
        language: str = "en",
        **kwargs
    ) -> AsyncIterator[AudioChunk]:
        """Generate audio stream from text."""
        pass
```

### AudioChunk (Data Type)

Audio data is returned as `AudioChunk`:

```python
@dataclass
class AudioChunk:
    """Audio data chunk."""
    data: bytes                    # Raw audio bytes
    sample_rate: int               # Sample rate in Hz
    channels: int = 1              # Number of channels
    format: str = "pcm_s16le"      # Audio format
```

## Plugin Loader

The core application loads plugins using `PluginLoader`:

```python
from tank_backend.plugin.loader import load_plugin

# Load TTS plugin
tts_engine = load_plugin("tts")

# Use plugin
async for chunk in tts_engine.generate_stream("Hello", language="en"):
    # Process audio chunk
    pass
```

### Loading Process

1. Read `plugins/plugins.yaml`
2. Find plugin configuration for slot (e.g., "tts")
3. Import plugin module: `plugins.<plugin-name>`
4. Call `create_engine(config)` factory function
5. Return engine instance

### Error Handling

- **Plugin not found** - Raises `ImportError`
- **Missing factory function** - Raises `AttributeError`
- **Invalid configuration** - Raises `ValueError`

## Best Practices

### 1. Follow Interface Contract

- Implement all abstract methods
- Use correct type hints
- Return expected data types

### 2. Handle Errors Gracefully

```python
async def generate_stream(self, text: str, language: str = "en", **kwargs):
    try:
        # Your implementation
        yield AudioChunk(...)
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        raise RuntimeError(f"Failed to generate audio: {e}") from e
```

### 3. Support Streaming

- Yield audio chunks as they're generated
- Don't buffer entire audio in memory
- Allow interruption via cancellation

### 4. Validate Configuration

```python
def __init__(self, config: dict):
    required = ["voice_en", "voice_zh"]
    for key in required:
        if key not in config:
            raise ValueError(f"Missing required config: {key}")
    self.config = config
```

### 5. Write Tests

- Test engine creation
- Test audio generation
- Test error handling
- Test configuration validation

### 6. Document Your Plugin

- README.md with usage examples
- Docstrings for all public methods
- Configuration options
- Dependencies

## Testing Plugins

### Unit Tests

```bash
cd backend/plugins/tts-myplugin
uv run pytest
```

### Integration Tests

```bash
cd backend
uv run pytest core/tests/ plugins/tts-myplugin/tests/
```

### Manual Testing

```bash
cd backend/core
uv run tank-backend
# Connect with CLI or web client
```

## Troubleshooting

### Plugin Not Loading

1. Check `plugins/plugins.yaml` syntax
2. Verify plugin folder name matches configuration
3. Check `create_engine` function exists
4. Review backend logs for errors

### Import Errors

1. Ensure plugin is in workspace (`backend/pyproject.toml`)
2. Run `uv sync` to install dependencies
3. Check Python path includes plugin directory

### Configuration Errors

1. Validate YAML syntax in `plugins/plugins.yaml`
2. Check required configuration keys
3. Verify data types match expectations

## Future Plugin Types

Planned plugin slots:

- **asr** - Automatic Speech Recognition
- **llm** - Large Language Model
- **embedding** - Speaker/text embeddings
- **vad** - Voice Activity Detection

## Contributing

1. Fork the repository
2. Create plugin following this guide
3. Add tests (minimum 80% coverage)
4. Update documentation
5. Submit pull request

## Resources

- [TTSEngine Interface](../contracts/tank_contracts/tts.py)
- [Edge TTS Plugin](tts-edge/) - Reference implementation
- [Backend Architecture](../ARCHITECTURE.md)
- [Development Guide](../DEVELOPMENT.md)

---

**Plugin System Version**: 1.0.0
**Status**: ✅ Production ready
**Supported Slots**: TTS
