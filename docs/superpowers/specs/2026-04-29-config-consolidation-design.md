# Config Class Consolidation

**Date:** 2026-04-29
**Status:** Approved

## Problem

The backend has 6 duplicated config dataclasses — a canonical version in `config/models.py` and local copies in individual modules. Additionally, `plugin/config.py` wraps `config/app_config.py`'s `AppConfig` as a backward-compatibility layer that is no longer needed.

This causes:
- Schema drift (local copies missing fields or having different names)
- Confusion about which import to use
- Extra indirection with no benefit

## Duplicates Found

| Config Class | Canonical | Local | Issue |
|---|---|---|---|
| AppConfig | config/app_config.py | plugin/config.py | Wrapper with no added value |
| EchoGuardConfig | config/models.py | pipeline/processors/echo_guard.py | Duplicate + adapter method |
| ContextConfig | config/models.py | context/config.py | Local has 4 extra fields |
| SandboxConfig | config/models.py | sandbox/config.py | Completely different field sets |
| MemoryConfig | config/models.py | memory/config.py | Identical + redundant from_dict() |
| PreferenceConfig | config/models.py | preferences/config.py | Local missing auto_learn |

## Design

### 1. Merge missing fields into config/models.py

**ContextConfig** — add from local:
- `max_history_tokens: int = 8000`
- `keep_recent_messages: int = 5`
- `summary_max_tokens: int = 500`
- `summary_temperature: float = 0.3`

**SandboxConfig** — add from local, rename `timeout` → `default_timeout`:
- `image: str = "tank-sandbox:latest"`
- `workspace_host_path: str = "./workspace"`
- `network_enabled: bool = True`
- Rename: `timeout: int = 120` → `default_timeout: int = 120`
- Keep existing: `backend`, `mounts`, `denied_mounts`, `docker`

**EchoGuardConfig** — no changes needed (already complete).

**MemoryConfig** — no changes needed (already complete).

**PreferenceConfig** — no changes needed (already has `auto_learn`).

### 2. Move find_config_yaml() into config/app_config.py

Move the `find_config_yaml()` function from `plugin/config.py` into `config/app_config.py`. Update `AppConfig.load()` to use it as the default when `config_path` is `None`.

### 3. Delete local config files

| File to delete | Action |
|---|---|
| `context/config.py` | Delete entirely |
| `sandbox/config.py` | Delete entirely |
| `memory/config.py` | Delete entirely |
| `preferences/config.py` | Delete entirely |

For `pipeline/processors/echo_guard.py`: remove the local `EchoGuardConfig` class and `from_typed()` classmethod. Import `EchoGuardConfig` from `..config.models` instead.

### 4. Delete plugin/config.py

Remove the entire file. Update callers to import from `config.app_config`:

| Caller | Old import | New import |
|---|---|---|
| `core/assistant.py` | `from ..plugin.config import AppConfig` | `from ..config.app_config import AppConfig` |
| `api/server.py` | `from ..plugin.config import AppConfig` | `from ..config.app_config import AppConfig` |
| `jobs/delivery.py` | `from ..plugin.config import AppConfig` | `from ..config.app_config import AppConfig` |
| `jobs/runner.py` | `from ..plugin.config import AppConfig` | `from ..config.app_config import AppConfig` |
| `plugin/__init__.py` | re-exports AppConfig | Remove re-export |

### 5. Update local module imports

| Module | Old import | New import |
|---|---|---|
| `context/manager.py` | `from .config import ContextConfig` | `from ..config.models import ContextConfig` |
| `context/summarizer.py` | `from .config import ContextConfig` | `from ..config.models import ContextConfig` |
| `context/__init__.py` | `from .config import ContextConfig` | `from ..config.models import ContextConfig` |
| `sandbox/factory.py` | `from .config import SandboxConfig` | `from ..config.models import SandboxConfig` |
| `sandbox/manager.py` | `from .config import SandboxConfig` | `from ..config.models import SandboxConfig` |
| `sandbox/__init__.py` | `from .config import SandboxConfig` | `from ..config.models import SandboxConfig` |
| `memory/service.py` | `from .config import MemoryConfig` | `from ..config.models import MemoryConfig` |
| `memory/__init__.py` | `from .config import MemoryConfig` | `from ..config.models import MemoryConfig` |
| `preferences/__init__.py` | `from .config import PreferenceConfig` | `from ..config.models import PreferenceConfig` |
| `pipeline/processors/brain.py` | `from .echo_guard import EchoGuardConfig` | `from ...config.models import EchoGuardConfig` |

### 6. Backward-compat aliases

Keep minimal re-exports in `plugin/__init__.py` for any external consumers:

```python
from ..config.app_config import AppConfig, FeatureConfig

PluginConfig = AppConfig
SlotConfig = FeatureConfig
```

### 7. Remove from_dict() methods

The local `from_dict()` / `from_typed()` classmethods are redundant — `config/parser.py::parse_section()` handles dict→dataclass conversion. Callers that used `from_dict()` should use `parse_section()` instead.

### 8. Tests

- Update any test imports that reference deleted modules
- Run full verification checklist (pytest, ruff, pyright on changed files, dev server check, E2E)

## Files Changed (Summary)

**Modified:**
- `config/models.py` — add fields to ContextConfig, SandboxConfig
- `config/app_config.py` — add `find_config_yaml()`, update `load()` signature
- `pipeline/processors/echo_guard.py` — remove local EchoGuardConfig, update imports
- `context/manager.py`, `context/summarizer.py`, `context/__init__.py` — update imports
- `sandbox/factory.py`, `sandbox/manager.py`, `sandbox/__init__.py` — update imports
- `memory/service.py`, `memory/__init__.py` — update imports
- `preferences/__init__.py` — update imports
- `core/assistant.py`, `api/server.py`, `jobs/delivery.py`, `jobs/runner.py` — update imports
- `plugin/__init__.py` — slim down to re-exports only
- Test files — update imports

**Deleted:**
- `plugin/config.py`
- `context/config.py`
- `sandbox/config.py`
- `memory/config.py`
- `preferences/config.py`

## Risks

- **SandboxConfig field rename** (`timeout` → `default_timeout`): any code accessing `.timeout` will break at runtime. Pyright on changed files will catch this.
- **Import breakage**: any module importing from deleted files will fail immediately on import. The test suite and dev server reload will surface these.
- **config.yaml parsing**: the `__config_flatten__` metadata on models controls YAML parsing behavior. Merged fields must work with the existing `parse_section()` logic — verify with unit tests.
