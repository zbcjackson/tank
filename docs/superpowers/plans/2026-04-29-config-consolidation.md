# Config Class Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all duplicated config dataclasses — single source of truth in `config/models.py`, single `AppConfig` in `config/app_config.py`, delete all local copies.

**Architecture:** Merge missing fields into canonical models, move `find_config_yaml()` into `config/app_config.py`, update all imports to point at canonical locations, delete local config files and the plugin/config.py wrapper.

**Tech Stack:** Python dataclasses, pytest, ruff, pyright

---

### Task 1: Merge missing fields into config/models.py

**Files:**
- Modify: `core/src/tank_backend/config/models.py`

- [ ] **Step 1: Add fields to ContextConfig**

In `core/src/tank_backend/config/models.py`, replace the `ContextConfig` class:

```python
@dataclass(frozen=True)
class ContextConfig:
    """``context:`` section."""

    max_history_tokens: int = 8000
    keep_recent_messages: int = 5
    summary_max_tokens: int = 500
    summary_temperature: float = 0.3
    store_type: str = "file"
    store_path: str = "~/.tank/sessions"
```

- [ ] **Step 2: Add fields to SandboxConfig and rename timeout**

In the same file, replace the `SandboxConfig` class:

```python
@dataclass(frozen=True)
class SandboxConfig:
    """``sandbox:`` section (raw mounts/docker kept as dicts)."""

    enabled: bool = True
    backend: str = "auto"
    image: str = "tank-sandbox:latest"
    workspace_host_path: str = "./workspace"
    mounts: list[dict[str, str]] = field(default_factory=list)
    denied_mounts: list[str] = field(default_factory=list)
    memory_limit: str = "1g"
    cpu_count: int = 2
    default_timeout: int = 120
    max_timeout: int = 600
    network_enabled: bool = True
    docker: dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 3: Run tests to verify models still parse correctly**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/test_config*.py -v`
Expected: All config tests pass (field additions are backward-compatible due to defaults).

- [ ] **Step 4: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add core/src/tank_backend/config/models.py
git commit -m "refactor: merge missing fields into canonical ContextConfig and SandboxConfig"
```

---

### Task 2: Move find_config_yaml() into config/app_config.py

**Files:**
- Modify: `core/src/tank_backend/config/app_config.py`
- Modify: `core/src/tank_backend/config/__init__.py`

- [ ] **Step 1: Add find_config_yaml() to config/app_config.py**

Add this function before the `AppConfig` class definition in `core/src/tank_backend/config/app_config.py`, after the existing imports. Add `from pathlib import Path` (already imported) and keep the existing imports:

```python
def find_config_yaml() -> Path:
    """Locate ``core/config.yaml`` by walking up from this file and CWD.

    Search order:
      1. Ancestors of this source file (works inside the installed package).
      2. Ancestors of the current working directory (works for scripts).

    Raises:
        FileNotFoundError: If the file cannot be found.
    """
    roots = [Path(__file__).resolve(), Path.cwd().resolve()]
    for root in roots:
        for parent in (root, *root.parents):
            candidate = parent / "core" / "config.yaml"
            if candidate.exists():
                return candidate
    raise FileNotFoundError(
        "Could not find core/config.yaml. "
        "Make sure you're running from the project root or backend/ directory."
    )
```

- [ ] **Step 2: Update AppConfig.load() to default to find_config_yaml()**

In the same file, change the `load` classmethod signature:

```python
    @classmethod
    def load(cls, config_path: Path | str | None = None, registry: object | None = None) -> AppConfig:
        """Load from a YAML file with env-var interpolation."""
        from ..plugin.yaml_loader import load_yaml

        if config_path is None:
            config_path = find_config_yaml()
        raw = load_yaml(config_path)
        logger.info("Loaded config from %s", config_path)
        cfg = cls.from_raw_dict(raw)
        if registry is not None:
            cls._validate_features(cfg, registry)
        return cfg
```

- [ ] **Step 3: Export find_config_yaml from config/__init__.py**

Add `find_config_yaml` to the imports and `__all__` in `core/src/tank_backend/config/__init__.py`:

```python
from .app_config import AppConfig, ConfigError, FeatureConfig, find_config_yaml
```

And add `"find_config_yaml"` to the `__all__` list.

- [ ] **Step 4: Run tests**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/ -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add core/src/tank_backend/config/app_config.py core/src/tank_backend/config/__init__.py
git commit -m "refactor: move find_config_yaml() into config/app_config.py"
```

---

### Task 3: Remove local EchoGuardConfig from echo_guard.py

**Files:**
- Modify: `core/src/tank_backend/pipeline/processors/echo_guard.py`
- Modify: `core/src/tank_backend/pipeline/processors/__init__.py`
- Modify: `core/src/tank_backend/pipeline/processors/brain.py`
- Modify: `core/src/tank_backend/core/assistant.py`

- [ ] **Step 1: Remove EchoGuardConfig class from echo_guard.py**

In `core/src/tank_backend/pipeline/processors/echo_guard.py`:
- Remove the entire `EchoGuardConfig` dataclass (lines 29-47, including the `from_typed` classmethod)
- Add an import at the top: `from ...config.models import EchoGuardConfig`

The file should keep `_TTSEntry`, `_tokenize`, and `SelfEchoDetector` unchanged. The `SelfEchoDetector.__init__` already accepts `EchoGuardConfig | None` — it will now use the canonical one.

- [ ] **Step 2: Update processors/__init__.py**

In `core/src/tank_backend/pipeline/processors/__init__.py`, change:

```python
from .echo_guard import EchoGuardConfig, SelfEchoDetector
```

to:

```python
from ...config.models import EchoGuardConfig
from .echo_guard import SelfEchoDetector
```

Wait — `__init__.py` is inside `pipeline/processors/`, so relative to that the config is at `...config.models`. Actually let's check: `pipeline/processors/__init__.py` → up to `pipeline/` → up to `tank_backend/` → into `config/`. That's `from ...config.models import EchoGuardConfig`. Correct.

- [ ] **Step 3: Update brain.py import**

In `core/src/tank_backend/pipeline/processors/brain.py`, change line 23:

```python
from .echo_guard import EchoGuardConfig, SelfEchoDetector
```

to:

```python
from ...config.models import EchoGuardConfig
from .echo_guard import SelfEchoDetector
```

- [ ] **Step 4: Update assistant.py — remove from_typed() call**

In `core/src/tank_backend/core/assistant.py`, the line:

```python
echo_guard_cfg = EchoGuardConfig.from_typed(self._app_config.echo_guard)
```

Since `self._app_config.echo_guard` already returns the canonical `EchoGuardConfig` from `config/models.py` (the typed AppConfig property), and the local `EchoGuardConfig` had identical fields, we can just use it directly:

```python
echo_guard_cfg = self._app_config.echo_guard
```

Also update the import in `assistant.py`. Currently it imports `EchoGuardConfig` from `..pipeline.processors`. Change:

```python
from ..pipeline.processors import (
    ASRProcessor,
    ASRSpeakerMerger,
    Brain,
    EchoGuardConfig,
    PlaybackProcessor,
    SpeakerIDProcessor,
    TTSProcessor,
    VADProcessor,
)
```

to:

```python
from ..pipeline.processors import (
    ASRProcessor,
    ASRSpeakerMerger,
    Brain,
    PlaybackProcessor,
    SpeakerIDProcessor,
    TTSProcessor,
    VADProcessor,
)
```

(Remove `EchoGuardConfig` from that import — it's no longer needed since we use `self._app_config.echo_guard` directly.)

- [ ] **Step 5: Run tests**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/ -q`
Expected: All tests pass.

- [ ] **Step 6: Run pyright on changed files**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pyright core/src/tank_backend/pipeline/processors/echo_guard.py core/src/tank_backend/pipeline/processors/__init__.py core/src/tank_backend/pipeline/processors/brain.py core/src/tank_backend/core/assistant.py`
Expected: No new errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add core/src/tank_backend/pipeline/processors/echo_guard.py \
        core/src/tank_backend/pipeline/processors/__init__.py \
        core/src/tank_backend/pipeline/processors/brain.py \
        core/src/tank_backend/core/assistant.py
git commit -m "refactor: remove local EchoGuardConfig, use canonical from config.models"
```

---

### Task 4: Delete context/config.py, update imports

**Files:**
- Delete: `core/src/tank_backend/context/config.py`
- Modify: `core/src/tank_backend/context/__init__.py`
- Modify: `core/src/tank_backend/context/manager.py`
- Modify: `core/src/tank_backend/context/summarizer.py`
- Modify: `core/tests/test_context_manager.py`

- [ ] **Step 1: Update context/__init__.py**

Change:

```python
from .config import ContextConfig
```

to:

```python
from ..config.models import ContextConfig
```

Keep `ContextConfig` in `__all__`.

- [ ] **Step 2: Update context/manager.py**

Change line 12:

```python
from .config import ContextConfig
```

to:

```python
from ..config.models import ContextConfig
```

- [ ] **Step 3: Update context/summarizer.py**

Change line 8:

```python
from .config import ContextConfig
```

to:

```python
from ..config.models import ContextConfig
```

- [ ] **Step 4: Update test_context_manager.py**

Change:

```python
from tank_backend.context.config import ContextConfig
```

to:

```python
from tank_backend.config.models import ContextConfig
```

- [ ] **Step 5: Delete context/config.py**

```bash
rm /Users/zbcjackson/src/tank/backend/core/src/tank_backend/context/config.py
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/test_context_manager.py -v`
Expected: All context tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add -A core/src/tank_backend/context/ core/tests/test_context_manager.py
git commit -m "refactor: delete context/config.py, import ContextConfig from config.models"
```

---

### Task 5: Delete memory/config.py, update imports

**Files:**
- Delete: `core/src/tank_backend/memory/config.py`
- Modify: `core/src/tank_backend/memory/__init__.py`
- Modify: `core/src/tank_backend/memory/service.py`
- Modify: `core/tests/test_memory.py`

- [ ] **Step 1: Update memory/__init__.py**

Change:

```python
from .config import MemoryConfig
```

to:

```python
from ..config.models import MemoryConfig
```

Keep `MemoryConfig` in `__all__`.

- [ ] **Step 2: Update memory/service.py**

Change line 10:

```python
from .config import MemoryConfig
```

to:

```python
from ..config.models import MemoryConfig
```

- [ ] **Step 3: Update test_memory.py**

Change:

```python
from tank_backend.memory.config import MemoryConfig
```

to:

```python
from tank_backend.config.models import MemoryConfig
```

- [ ] **Step 4: Check for from_dict() callers in memory/service.py**

Grep for `MemoryConfig.from_dict` in the codebase. If found, replace with `parse_section(MemoryConfig, raw_dict)` using `from tank_backend.config.parser import parse_section`.

Run: `cd /Users/zbcjackson/src/tank/backend && grep -r "MemoryConfig.from_dict\|MemoryConfig\.from_dict" core/`

If no callers found, proceed to delete.

- [ ] **Step 5: Delete memory/config.py**

```bash
rm /Users/zbcjackson/src/tank/backend/core/src/tank_backend/memory/config.py
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/test_memory.py -v`
Expected: All memory tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add -A core/src/tank_backend/memory/ core/tests/test_memory.py
git commit -m "refactor: delete memory/config.py, import MemoryConfig from config.models"
```

---

### Task 6: Delete preferences/config.py, update imports

**Files:**
- Delete: `core/src/tank_backend/preferences/config.py`
- Modify: `core/src/tank_backend/preferences/__init__.py`

- [ ] **Step 1: Update preferences/__init__.py**

Change:

```python
from .config import PreferenceConfig
```

to:

```python
from ..config.models import PreferenceConfig
```

Keep `PreferenceConfig` in `__all__`.

- [ ] **Step 2: Check for from_dict() callers**

Run: `cd /Users/zbcjackson/src/tank/backend && grep -r "PreferenceConfig.from_dict\|PreferenceConfig\.from_dict" core/`

If found, replace with `parse_section(PreferenceConfig, raw_dict)`.

- [ ] **Step 3: Delete preferences/config.py**

```bash
rm /Users/zbcjackson/src/tank/backend/core/src/tank_backend/preferences/config.py
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/ -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add -A core/src/tank_backend/preferences/
git commit -m "refactor: delete preferences/config.py, import PreferenceConfig from config.models"
```

---

### Task 7: Delete sandbox/config.py, update imports

**Files:**
- Delete: `core/src/tank_backend/sandbox/config.py`
- Modify: `core/src/tank_backend/sandbox/__init__.py`
- Modify: `core/src/tank_backend/sandbox/manager.py`
- Modify: `core/tests/test_sandbox_manager.py`

- [ ] **Step 1: Update sandbox/__init__.py**

Change:

```python
from .config import SandboxConfig
```

to:

```python
from ..config.models import SandboxConfig
```

Keep `SandboxConfig` in `__all__`.

- [ ] **Step 2: Update sandbox/manager.py**

Change line 15:

```python
from .config import SandboxConfig
```

to:

```python
from ..config.models import SandboxConfig
```

- [ ] **Step 3: Update test_sandbox_manager.py**

Change:

```python
from tank_backend.sandbox.config import SandboxConfig
```

to:

```python
from tank_backend.config.models import SandboxConfig
```

- [ ] **Step 4: Fix any .timeout references → .default_timeout**

The canonical `SandboxConfig` now uses `default_timeout` (renamed from `timeout`). Grep for `.timeout` usage in sandbox code:

Run: `cd /Users/zbcjackson/src/tank/backend && grep -rn "\.timeout" core/src/tank_backend/sandbox/ core/tests/test_sandbox*`

Replace any `config.timeout` with `config.default_timeout`. Note: be careful not to replace unrelated `.timeout` references (e.g., `asyncio.timeout`).

- [ ] **Step 5: Check for from_dict() callers**

Run: `cd /Users/zbcjackson/src/tank/backend && grep -r "SandboxConfig.from_dict\|SandboxConfig\.from_dict" core/`

If found, replace with `parse_section(SandboxConfig, raw_dict)` using `from tank_backend.config.parser import parse_section`.

- [ ] **Step 6: Delete sandbox/config.py**

```bash
rm /Users/zbcjackson/src/tank/backend/core/src/tank_backend/sandbox/config.py
```

- [ ] **Step 7: Run tests**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/test_sandbox_manager.py -v`
Expected: All sandbox tests pass.

- [ ] **Step 8: Run pyright on sandbox files**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pyright core/src/tank_backend/sandbox/manager.py core/src/tank_backend/sandbox/factory.py`
Expected: No new errors (catches `.timeout` → `.default_timeout` misses).

- [ ] **Step 9: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add -A core/src/tank_backend/sandbox/ core/tests/test_sandbox_manager.py
git commit -m "refactor: delete sandbox/config.py, import SandboxConfig from config.models"
```

---

### Task 8: Delete plugin/config.py, update all callers

**Files:**
- Delete: `core/src/tank_backend/plugin/config.py`
- Modify: `core/src/tank_backend/plugin/__init__.py`
- Modify: `core/src/tank_backend/core/assistant.py`
- Modify: `core/src/tank_backend/api/server.py`
- Modify: `core/src/tank_backend/jobs/delivery.py`
- Modify: `core/src/tank_backend/jobs/runner.py`
- Modify: `core/tests/test_brain_typed_config.py`
- Modify: `core/tests/test_plugin_switch.py`

- [ ] **Step 1: Update core/assistant.py**

Change:

```python
from ..plugin import AppConfig
```

to:

```python
from ..config import AppConfig
```

- [ ] **Step 2: Update api/server.py**

Change:

```python
from ..plugin import AppConfig  # noqa: E402
```

to:

```python
from ..config import AppConfig  # noqa: E402
```

- [ ] **Step 3: Update jobs/delivery.py**

Change the TYPE_CHECKING import:

```python
    from ..plugin import AppConfig
```

to:

```python
    from ..config import AppConfig
```

- [ ] **Step 4: Update jobs/runner.py**

Change the TYPE_CHECKING import:

```python
    from ..plugin import AppConfig
```

to:

```python
    from ..config import AppConfig
```

- [ ] **Step 5: Update plugin/__init__.py**

Replace the entire file with minimal re-exports:

```python
"""Plugin system for Tank backend."""

from ..config import AppConfig, FeatureConfig, find_config_yaml
from .manager import ConfigError, PluginManager
from .manifest import (
    ExtensionManifest,
    PluginManifest,
    read_manifest_from_yaml,
    read_plugin_manifest,
)
from .registry import ExtensionRegistry

# Backward-compat aliases
PluginConfig = AppConfig
SlotConfig = FeatureConfig

__all__ = [
    "AppConfig",
    "ConfigError",
    "ExtensionManifest",
    "ExtensionRegistry",
    "FeatureConfig",
    "PluginConfig",
    "PluginManager",
    "PluginManifest",
    "SlotConfig",
    "find_config_yaml",
    "read_manifest_from_yaml",
    "read_plugin_manifest",
]
```

- [ ] **Step 6: Update test_brain_typed_config.py**

Change:

```python
from tank_backend.plugin.config import AppConfig
```

to:

```python
from tank_backend.config import AppConfig
```

- [ ] **Step 7: Update test_plugin_switch.py**

Change:

```python
from tank_backend.plugin.config import AppConfig
```

to:

```python
from tank_backend.config import AppConfig
```

- [ ] **Step 8: Delete plugin/config.py**

```bash
rm /Users/zbcjackson/src/tank/backend/core/src/tank_backend/plugin/config.py
```

- [ ] **Step 9: Run full test suite**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/ -q`
Expected: All tests pass.

- [ ] **Step 10: Run ruff**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run ruff check core/src/ core/tests/`
Expected: No errors.

- [ ] **Step 11: Run pyright on key changed files**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pyright core/src/tank_backend/core/assistant.py core/src/tank_backend/api/server.py core/src/tank_backend/plugin/__init__.py`
Expected: No new errors.

- [ ] **Step 12: Commit**

```bash
cd /Users/zbcjackson/src/tank/backend
git add -A core/src/tank_backend/plugin/ core/src/tank_backend/core/assistant.py \
        core/src/tank_backend/api/server.py core/src/tank_backend/jobs/ \
        core/tests/test_brain_typed_config.py core/tests/test_plugin_switch.py
git commit -m "refactor: delete plugin/config.py wrapper, callers import from config/ directly"
```

---

### Task 9: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run pytest core/tests/ -q`
Expected: All tests pass.

- [ ] **Step 2: Run ruff on entire backend**

Run: `cd /Users/zbcjackson/src/tank/backend && uv run ruff check core/src/ core/tests/`
Expected: No errors.

- [ ] **Step 3: Check dev server starts without errors**

Run: `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`
Expected: No errors related to config imports.

If the dev server is not running, start it and check:
```bash
cd /Users/zbcjackson/src/tank && ./scripts/dev.sh
sleep 5
tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"
```

- [ ] **Step 4: Verify deleted files are gone**

```bash
ls /Users/zbcjackson/src/tank/backend/core/src/tank_backend/plugin/config.py 2>&1
ls /Users/zbcjackson/src/tank/backend/core/src/tank_backend/context/config.py 2>&1
ls /Users/zbcjackson/src/tank/backend/core/src/tank_backend/sandbox/config.py 2>&1
ls /Users/zbcjackson/src/tank/backend/core/src/tank_backend/memory/config.py 2>&1
ls /Users/zbcjackson/src/tank/backend/core/src/tank_backend/preferences/config.py 2>&1
```

Expected: All return "No such file or directory".

- [ ] **Step 5: Run E2E tests (if backend + frontend running)**

Run: `cd /Users/zbcjackson/src/tank/test && pnpm test`
Expected: All E2E scenarios pass.
