# Tank Contracts

Lightweight package containing abstract base classes (ABCs) for Tank plugins.

## Purpose

This package defines the contracts that plugins must implement:
- `TTSEngine` - Text-to-Speech engine interface
- `AudioChunk` - Audio data type
- Future: `ASREngine`, `LLMEngine`, etc.

Both the backend and plugins depend on this package, ensuring they agree on the interface without creating circular dependencies.

## Usage

```python
from tank_contracts.tts import TTSEngine, AudioChunk

class MyTTSEngine(TTSEngine):
    async def generate_stream(self, text, **kwargs):
        # Implementation
        yield AudioChunk(data=b"...", sample_rate=24000, channels=1)
```
