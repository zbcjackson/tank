# Tank Contracts

Shared interfaces and abstract base classes for Tank plugins.

## Purpose

This package defines the contracts that plugins must implement to integrate with the Tank backend. It provides a clean separation between the core application and pluggable components.

**Key Benefits:**
- **Interface stability** - Plugins depend on stable ABCs, not core implementation
- **No circular dependencies** - Both core and plugins depend on contracts
- **Type safety** - Clear interfaces with type hints
- **Extensibility** - Easy to add new plugin types (ASR, LLM, etc.)

## Current Contracts

### TTSEngine

Abstract base class for Text-to-Speech engines.

```python
from tank_contracts.tts import TTSEngine, AudioChunk

class MyTTSEngine(TTSEngine):
    """Custom TTS engine implementation."""

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
            **kwargs: Engine-specific parameters

        Yields:
            AudioChunk: Audio data chunks
        """
        # Implementation
        yield AudioChunk(
            data=b"...",           # Raw audio bytes
            sample_rate=24000,     # Sample rate in Hz
            channels=1,            # Number of channels
            format="pcm_s16le"     # Audio format
        )
```

### AudioChunk

Data class representing a chunk of audio data.

```python
@dataclass
class AudioChunk:
    """Audio data chunk."""
    data: bytes                    # Raw audio bytes
    sample_rate: int               # Sample rate in Hz
    channels: int = 1              # Number of channels
    format: str = "pcm_s16le"      # Audio format
```

## Future Contracts

Planned interfaces for future plugin types:

- **ASREngine** - Automatic Speech Recognition
- **LLMEngine** - Large Language Model
- **EmbeddingEngine** - Speaker/text embeddings
- **VADEngine** - Voice Activity Detection

## Installation

This package is automatically installed as part of the backend workspace:

```bash
cd backend
uv sync
```

Or install standalone:

```bash
cd backend/contracts
uv pip install -e .
```

## Usage in Plugins

### 1. Add Dependency

In your plugin's `pyproject.toml`:

```toml
[project]
dependencies = [
    "tank-contracts",
]
```

### 2. Implement Interface

```python
from tank_contracts.tts import TTSEngine, AudioChunk
from typing import AsyncIterator

class MyTTSEngine(TTSEngine):
    def __init__(self, config: dict):
        self.config = config
        # Initialize your TTS engine

    async def generate_stream(
        self,
        text: str,
        language: str = "en",
        **kwargs
    ) -> AsyncIterator[AudioChunk]:
        # Your implementation
        audio_data = await self._synthesize(text, language)
        yield AudioChunk(
            data=audio_data,
            sample_rate=24000,
            channels=1
        )

    async def _synthesize(self, text: str, language: str) -> bytes:
        # TTS synthesis logic
        pass
```

### 3. Export Factory Function

```python
def create_engine(config: dict) -> TTSEngine:
    """Factory function called by plugin loader."""
    return MyTTSEngine(config)
```

## Usage in Core

The core application uses contracts to interact with plugins:

```python
from tank_contracts.tts import TTSEngine, AudioChunk

class AudioOutput:
    def __init__(self, tts_engine: TTSEngine):
        self.tts_engine = tts_engine

    async def speak(self, text: str, language: str):
        async for chunk in self.tts_engine.generate_stream(text, language):
            await self._play_chunk(chunk)
```

## Development

### Adding a New Contract

1. Create new module in `tank_contracts/`
2. Define abstract base class with `@abstractmethod`
3. Add type hints for all parameters and return values
4. Document the interface with docstrings
5. Export from `__init__.py`

Example:

```python
# tank_contracts/asr.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class Transcript:
    """ASR transcript result."""
    text: str
    language: str
    confidence: float

class ASREngine(ABC):
    """Abstract base class for ASR engines."""

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        **kwargs
    ) -> AsyncIterator[Transcript]:
        """Transcribe audio stream to text."""
        pass
```

### Testing

Test your contract implementations:

```python
import pytest
from tank_contracts.tts import TTSEngine, AudioChunk

async def test_tts_engine_generates_audio():
    engine = MyTTSEngine(config={})
    chunks = []

    async for chunk in engine.generate_stream("Hello world", language="en"):
        assert isinstance(chunk, AudioChunk)
        assert chunk.sample_rate > 0
        assert len(chunk.data) > 0
        chunks.append(chunk)

    assert len(chunks) > 0
```

## Versioning

The contracts package follows semantic versioning:

- **Major version** - Breaking changes to interfaces
- **Minor version** - New interfaces or optional parameters
- **Patch version** - Bug fixes, documentation

Plugins should specify compatible contract versions:

```toml
[project]
dependencies = [
    "tank-contracts>=1.0.0,<2.0.0",
]
```

## Documentation

- [TTSEngine API](tank_contracts/tts.py) - Full TTS interface documentation
- [Plugin Development Guide](../plugins/README.md) - How to create plugins
- [Backend Architecture](../ARCHITECTURE.md) - How contracts fit into the system

---

**Package**: `tank-contracts`
**Version**: 1.0.0
**License**: MIT
