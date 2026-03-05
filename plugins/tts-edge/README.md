# Edge TTS Plugin

Microsoft Edge TTS plugin for Tank Voice Assistant.

## Features

- Streaming TTS generation with low latency
- Supports 100+ voices in multiple languages
- MP3 → PCM decoding via ffmpeg (preferred) or pydub (fallback)
- Interruptible generation

## Configuration

```yaml
# plugins/plugins.yaml
tts:
  plugin: tts-edge
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
```

## Dependencies

- `edge-tts>=6.1.0` - Microsoft Edge TTS client
- `pydub>=0.25.0` - Audio processing (MP3 decoding fallback)
- `ffmpeg` (optional, recommended) - Fast MP3 decoding

## Installation

This plugin is installed automatically as part of the Tank workspace:

```bash
cd /path/to/tank
uv sync
```

## Testing

```bash
cd plugins/tts-edge
uv run pytest
```

## Available Voices

See [Microsoft Edge TTS voices](https://speech.microsoft.com/portal/voicegallery) for the full list.

Popular choices:
- English: `en-US-JennyNeural`, `en-US-GuyNeural`, `en-GB-SoniaNeural`
- Chinese: `zh-CN-XiaoxiaoNeural`, `zh-CN-YunxiNeural`, `zh-TW-HsiaoChenNeural`
