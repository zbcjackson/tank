# macOS App Testing Guidelines

This document provides testing guidelines for the Tank macOS native app.

## Overview

The macOS app is a thin Tauri shell. Testing is split across layers:

| Layer | What to test | Where |
|-------|-------------|-------|
| Frontend UI | Components, hooks, services | `web/` (see `web/TESTING.md`) |
| Rust backend | Tauri commands, native logic | `macos/src-tauri/` |
| Integration | App launches, window loads | Manual / E2E |

## Rust Tests

### Framework

- **Framework**: built-in `cargo test`
- **Location**: inline `#[cfg(test)]` modules in `src-tauri/src/`

### Running tests

```bash
cd macos/src-tauri
cargo test
```

### Writing tests

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_my_command() {
        let result = my_pure_function("input");
        assert_eq!(result, "expected");
    }
}
```

### What to test in Rust

- Pure functions used by Tauri commands
- Data transformations and validation
- Error handling paths

### What NOT to test in Rust

- Tauri framework internals (window creation, IPC)
- The web frontend (tested in `web/`)

## Frontend Tests

All frontend testing is handled by the `web/` sub-project. See `web/TESTING.md`.

When adding Tauri-specific frontend code (e.g., `invoke()` calls), mock the Tauri API:

```typescript
vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));
```

## Integration / Manual Testing

Since the app is a thin wrapper, integration testing is primarily manual:

1. `pnpm dev` — verify the native window opens and loads the web UI
2. Test voice mode — microphone permission prompt should appear
3. Test chat mode — messages should flow through WebSocket
4. Test window controls — resize, minimize, close
5. Test title bar overlay — content should render under the title bar

## Quality Checklist

- [ ] `cargo check` passes (no compilation errors)
- [ ] `cargo clippy` passes (no lint warnings)
- [ ] `cargo fmt --check` passes (formatting)
- [ ] `cargo test` passes (if tests exist)
- [ ] App launches successfully with `pnpm dev`
- [ ] Web frontend loads in the native window
- [ ] WebSocket connection to backend works
