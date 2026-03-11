# Tank Plugins

Pluggable components for the Tank Voice Assistant backend.

## Overview

The Tank backend uses a plugin architecture to support different ASR, TTS, and speaker identification engines. Plugins are discovered automatically at startup via `[tool.tank]` manifests in their `pyproject.toml`, registered in an `ExtensionRegistry`, and instantiated on demand.

## Architecture

```
backend/
├── core/                    # Core application
│   └── src/tank_backend/
│       └── plugin/         # Plugin lifecycle (manager, registry, config)
├── contracts/              # Shared interfaces (TTSEngine, StreamingASREngine ABCs)
│   └── tank_contracts/
└── plugins/                # Plugin implementations
    ├── asr-sherpa/         # Sherpa-ONNX streaming ASR
    ├── asr-elevenlabs/     # ElevenLabs ASR
    ├── tts-edge/           # Edge TTS
    ├── tts-elevenlabs/     # ElevenLabs TTS
    ├── tts-cosyvoice/      # CosyVoice TTS
    └── speaker-sherpa/     # Sherpa-ONNX speaker identification
```

### How It Works

1. **Discovery** — `PluginManager` scans installed packages for `[tool.tank]` in `pyproject.toml`
2. **Inventory** — `plugins.yaml` (auto-generated on first run) controls per-plugin/extension enable/disable
3. **Registration** — enabled extensions are registered in `ExtensionRegistry` as manifests
4. **Validation** — `config.yaml` slot refs are checked against the registry at startup
5. **Instantiation** — `registry.instantiate("plugin:ext", config)` calls the factory on demand

### Startup Flow

```
PluginManager.load_all()
  ├── plugins.yaml missing? → discover_plugins() → generate_plugins_yaml()
  ├── Read plugins.yaml → PluginEntry list
  └── For each enabled plugin/extension: registry.register(plugin, manifest)

Assistant.__init__()
  ├── registry = PluginManager().load_all()
  ├── app_config = AppConfig(registry=registry)   ← validates extension refs
  ├── asr_engine = registry.instantiate("asr-sherpa:asr", config)
  ├── tts_engine = registry.instantiate("tts-edge:tts", config)
  ├── AudioInput(asr_engine=asr_engine)            ← receives pre-built engine
  └── AudioOutput(tts_engine=tts_engine)           ← receives pre-built engine
```

## Configuration

### Slot Assignment (`core/config.yaml`)

Each slot references a registered extension by `"plugin:extension"`:

```yaml
asr:
  extension: asr-sherpa:asr
  config:
    model_dir: ../models/sherpa-onnx-zipformer-en-zh
    num_threads: 4
    sample_rate: 16000

tts:
  extension: tts-edge:tts
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural

speaker:
  extension: speaker-sherpa:speaker_id
  config:
    db_path: ../data/speakers.db
    threshold: 0.6
```

Disable a slot by setting `enabled: false`:

```yaml
tts:
  enabled: false
  extension: tts-edge:tts
  config: {}
```

### Plugin Inventory (`core/plugins.yaml`)

Auto-generated on first run. Controls which plugins and extensions are active:

```yaml
asr-sherpa:
  enabled: true
  extensions:
    asr:
      enabled: true
tts-edge:
  enabled: true
  extensions:
    tts:
      enabled: true
speaker-sherpa:
  enabled: true
  extensions:
    speaker_id:
      enabled: true
```

You can disable a plugin or individual extension here without touching `config.yaml`.

## Available Plugins

### ASR Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| **asr-sherpa** | Sherpa-ONNX streaming ASR | ✅ Production |
| **asr-elevenlabs** | ElevenLabs realtime ASR | ✅ Production |

### TTS Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| **tts-edge** | Microsoft Edge TTS | ✅ Production |
| **tts-elevenlabs** | ElevenLabs TTS | ✅ Production |
| **tts-cosyvoice** | CosyVoice TTS (requires server) | ✅ Production |

### Speaker ID Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| **speaker-sherpa** | Sherpa-ONNX speaker embeddings | ✅ Production |

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

### 2. Implement the Contract

Create `tts_myplugin/engine.py`:

```python
from tank_contracts.tts import TTSEngine, AudioChunk
from typing import AsyncIterator

class MyTTSEngine(TTSEngine):
    """Custom TTS engine implementation."""

    def __init__(self, config: dict):
        self.config = config

    async def generate_stream(
        self,
        text: str,
        language: str = "en",
        **kwargs
    ) -> AsyncIterator[AudioChunk]:
        audio_data = await self._synthesize(text, language)
        yield AudioChunk(
            data=audio_data,
            sample_rate=24000,
            channels=1,
            format="pcm_s16le"
        )
```

### 3. Export Factory Function

Create `tts_myplugin/__init__.py`:

```python
from .engine import MyTTSEngine

def create_engine(config: dict) -> MyTTSEngine:
    """Factory function called by ExtensionRegistry.instantiate()."""
    return MyTTSEngine(config)

__all__ = ["create_engine", "MyTTSEngine"]
```

### 4. Declare Manifest in `pyproject.toml`

```toml
[project]
name = "tts-myplugin"
version = "1.0.0"
description = "My TTS plugin for Tank"
requires-python = ">=3.10"
dependencies = [
    "tank-contracts",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.tank]
plugin_name = "tts-myplugin"
display_name = "My TTS"
description = "My custom TTS plugin"

[[tool.tank.extensions]]
name = "tts"
type = "tts"
factory = "tts_myplugin:create_engine"

[tool.uv.sources]
tank-contracts = { workspace = true }
```

The `[tool.tank]` section is how `PluginManager` discovers your plugin. The `factory` field is `"module:callable"` — the registry calls this to create engine instances.

### 5. Add Tests

Create `tests/test_engine.py`:

```python
import pytest
from tts_myplugin import create_engine
from tank_contracts.tts import AudioChunk

@pytest.mark.asyncio
async def test_create_engine():
    engine = create_engine({"param": "value"})
    assert engine is not None

@pytest.mark.asyncio
async def test_generate_stream():
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

### 7. Configure and Run

```bash
# Install
cd backend
uv sync

# Delete plugins.yaml to trigger re-discovery
rm -f core/plugins.yaml

# Reference in core/config.yaml
# tts:
#   extension: tts-myplugin:tts
#   config:
#     param: value

# Run
cd core
uv run tank-backend
```

Or install programmatically:

```python
from tank_backend.plugin.manager import PluginManager
pm = PluginManager()
pm.load_all()
pm.install("tts-myplugin")
```

## Plugin Manifest Reference

The `[tool.tank]` section in `pyproject.toml`:

```toml
[tool.tank]
plugin_name = "tts-myplugin"     # Package name (must match [project].name)
display_name = "My TTS"          # Human-readable name
description = "Description"      # Short description

[[tool.tank.extensions]]         # One or more extensions
name = "tts"                     # Extension name (used in "plugin:ext" ref)
type = "tts"                     # Extension type: "asr" | "tts" | "speaker_id"
factory = "module:callable"      # Factory: "module_name:function_name"
```

A single plugin can provide multiple extensions (e.g., both ASR and TTS).

## Plugin Lifecycle API

```python
from tank_backend.plugin.manager import PluginManager

pm = PluginManager()
registry = pm.load_all()

# Discovery
plugins = pm.discover_plugins()          # Scan installed packages

# Install / Uninstall
pm.install("tts-myplugin")              # Add to plugins.yaml + register
pm.uninstall("tts-myplugin")            # Remove from plugins.yaml + unregister

# Enable / Disable (plugin level)
pm.disable_plugin("tts-edge")           # Unregister all extensions
pm.enable_plugin("tts-edge")            # Re-register extensions

# Enable / Disable (extension level)
pm.disable_extension("tts-edge", "tts") # Unregister single extension
pm.enable_extension("tts-edge", "tts")  # Re-register single extension

# Instantiation
engine = registry.instantiate("tts-edge:tts", {"voice_en": "Jenny"})

# Validation
pm.validate_config(app_config)           # Check config.yaml refs
```

## Best Practices

1. **Follow the contract** — implement all abstract methods from `tank_contracts`
2. **Stream audio** — yield chunks as they're generated, don't buffer in memory
3. **Handle errors** — raise `RuntimeError` with descriptive messages
4. **Validate config** — check required keys in `__init__`
5. **Write tests** — unit tests for engine, integration tests with core
6. **Document** — README with config options, usage examples, dependencies

## Troubleshooting

### Plugin Not Discovered

1. Ensure `[tool.tank]` section exists in `pyproject.toml`
2. Run `uv sync` to install the package
3. Delete `core/plugins.yaml` and restart to trigger re-discovery
4. Check logs for `"Discovered plugin: ..."` messages

### Extension Not Registered

1. Check `core/plugins.yaml` — is the plugin/extension `enabled: true`?
2. Verify the package is installed: `uv run python -c "import tts_myplugin"`

### Config Validation Error

1. Check `core/config.yaml` — does the `extension:` ref match a registered extension?
2. Verify the extension type matches the slot (e.g., `tts` slot expects `type = "tts"`)
3. Run: `uv run python -c "from tank_backend.plugin.manager import PluginManager; pm = PluginManager(); r = pm.load_all(); print(r.all_names())"`

## Resources

- [TTSEngine Interface](../contracts/tank_contracts/tts.py)
- [Edge TTS Plugin](tts-edge/) — TTS reference implementation
- [Sherpa ASR Plugin](asr-sherpa/) — ASR reference implementation
- [Backend Architecture](../ARCHITECTURE.md)
- [Development Guide](../DEVELOPMENT.md)
