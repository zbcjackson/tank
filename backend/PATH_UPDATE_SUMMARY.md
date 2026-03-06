# Path Update Summary - Backend Reorganization

**Date**: 2026-03-05

## Overview

After the backend reorganization, all `data/` and `models/` paths have been updated to reflect the new structure where the working directory is `backend/core/` but data and models are stored in `backend/`.

## Path Changes

All hardcoded paths have been updated from absolute paths to relative paths that work from `backend/core/`:

| Old Path | New Path | Reason |
|----------|----------|--------|
| `data/speakers.db` | `../data/speakers.db` | Data directory is one level up from core/ |
| `models/sherpa-onnx-zipformer-en-zh` | `../models/sherpa-onnx-zipformer-en-zh` | Models directory is one level up from core/ |
| `models/speaker/*.onnx` | `../models/speaker/*.onnx` | Models directory is one level up from core/ |

## Files Updated

### Source Code
1. **`backend/core/src/tank_backend/config/settings.py`**
   - `sherpa_model_dir` default: `../models/sherpa-onnx-zipformer-en-zh`
   - `speaker_model_path` default: `../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx`
   - `speaker_db_path` default: `../data/speakers.db`
   - Environment variable defaults updated
   - `.env.example` template updated

2. **`backend/core/src/tank_backend/audio/input/repository_sqlite.py`**
   - `SQLiteSpeakerRepository.__init__()` default: `../data/speakers.db`

3. **`backend/core/src/tank_backend/audio/input/types.py`**
   - `PerceptionConfig.sherpa_model_dir` default: `../models/sherpa-onnx-zipformer-en-zh`

### Scripts
4. **`backend/scripts/download_models.py`**
   - `ASR_DIR`: `../models/sherpa-onnx-zipformer-en-zh`
   - `SPEAKER_DIR`: `../models/speaker`

5. **`backend/scripts/manage_speakers.py`**
   - `--db` argument default: `../data/speakers.db`

### Configuration
6. **`backend/plugins/plugins.yaml`**
   - Comment example updated: `../models/sherpa-onnx-zipformer-en-zh`

## Working Directory

The backend is designed to run from `backend/core/`:

```bash
cd backend/core
uv run tank-backend
```

All relative paths (`../data/`, `../models/`) are resolved from this working directory.

## Directory Structure

```
backend/
├── core/                    # Working directory
│   ├── src/tank_backend/   # Source code (uses ../data, ../models)
│   ├── tests/              # Tests
│   └── .env                # Config file
├── data/                   # Runtime data (speakers.db, etc.)
├── models/                 # ML models (Whisper, Sherpa, speaker models)
├── scripts/                # Utility scripts (use ../data, ../models)
└── plugins/                # TTS plugins
```

## Verification

All tests pass after path updates:
```bash
cd backend/core
uv run pytest  # 107 passed ✅
uv run ruff check src/ tests/  # All checks passed ✅
```

## Environment Variables

Users can override default paths via environment variables:

```env
# In backend/core/.env
SHERPA_MODEL_DIR=../models/sherpa-onnx-zipformer-en-zh
SPEAKER_MODEL_PATH=../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
SPEAKER_DB_PATH=../data/speakers.db
```

Or use absolute paths:
```env
SPEAKER_DB_PATH=/absolute/path/to/speakers.db
```

## Migration Notes

- **No action required** for users who run from `backend/core/` (recommended)
- If running from a different directory, set absolute paths in `.env`
- Scripts in `backend/scripts/` automatically use relative paths from their location

---

**Status**: ✅ Complete
**Tests**: 107/107 passing
**Linting**: All checks passed
