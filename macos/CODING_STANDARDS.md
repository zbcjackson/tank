# macOS App Coding Standards

This document defines coding standards for the Tank macOS native app.

## Rust (src-tauri/)

### Style

- **Edition**: Rust 2021
- **Formatting**: `cargo fmt` (rustfmt defaults)
- **Linting**: `cargo clippy` — treat warnings as errors in CI
- **No `unwrap()` in production code** — use `expect()` with context or proper error handling

### Tauri Commands

When adding custom commands invocable from the frontend:

```rust
// ✅ Good: typed parameters, Result return, serde
#[tauri::command]
fn get_app_version(app: tauri::AppHandle) -> Result<String, String> {
    Ok(app.package_info().version.to_string())
}

// Register in lib.rs
tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![get_app_version])
    .run(tauri::generate_context!())
    .expect("error while running Tank");
```

```typescript
// Frontend usage (in web/src/)
import { invoke } from '@tauri-apps/api/core';
const version = await invoke<string>('get_app_version');
```

### Error Handling

- Return `Result<T, String>` from Tauri commands (Tauri serializes the error to JS)
- Use `thiserror` for custom error types if complexity grows
- Log errors with `log` crate, not `println!`

### Dependencies

- Keep Rust dependencies minimal — this is a thin shell
- Pin major versions in `Cargo.toml`
- Run `cargo update` periodically to pick up patch fixes

## Frontend (web/)

All frontend code lives in `web/`. Follow `web/CODING_STANDARDS.md` for TypeScript/React standards.

### Tauri-Specific Frontend Patterns

When using Tauri APIs from the web frontend:

```typescript
// ✅ Good: feature-detect Tauri environment
const isTauri = '__TAURI__' in window;

if (isTauri) {
  const { invoke } = await import('@tauri-apps/api/core');
  // Use native feature
} else {
  // Browser fallback
}
```

- Always feature-detect `__TAURI__` — the web app must still work in a regular browser
- Import `@tauri-apps/api` dynamically to avoid bundling it in the web-only build

## Configuration

### `tauri.conf.json`

- Keep window dimensions appropriate for the voice assistant UI (compact)
- Use `titleBarStyle: "Overlay"` for native macOS look
- Set `minimumSystemVersion` to the oldest macOS you support

### Capabilities

- Follow principle of least privilege — only grant permissions the app actually needs
- Document why each permission is needed in a comment or the capability description
