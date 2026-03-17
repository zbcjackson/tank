# macOS App Development Guide

This document provides development commands and workflows for the Tank macOS native app.

## Prerequisites

- **Rust toolchain** (rustc, cargo) — install via [rustup](https://rustup.rs/)
- **Node.js 18+**
- **pnpm**
- **Xcode Command Line Tools** (for macOS compilation)
- Tank Backend running on `localhost:8000`
- Tank Web Frontend dependencies installed (`cd web && pnpm install`)

## Setup

### 1. Install Rust (if not already installed)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Verify
rustc --version
cargo --version
```

### 2. Install Xcode Command Line Tools

```bash
xcode-select --install
```

### 3. Install JS dependencies

```bash
cd macos
pnpm install
```

### 4. Install Web Frontend dependencies

```bash
cd web
pnpm install
```

### 5. Verify setup

```bash
# From macos/
cargo --version          # Rust compiler
rustc --version          # Rust version
pnpm tauri --version     # Tauri CLI version
```

## Development

### Start dev mode

```bash
cd macos
pnpm dev
```

This will:
1. Check if `http://localhost:5173` (Vite dev server) is running
2. If not, start `pnpm --dir ../web dev` automatically
3. Compile the Rust backend (first run takes ~1-2 minutes)
4. Open a native macOS window loading the web frontend
5. HMR works — edit `web/src/` files and see changes instantly

> Make sure the Tank Backend is running on `localhost:8000` before starting.

### Common issues on first run

**"cargo not found"** — Rust is not installed. Run the rustup installer above.

**"failed to run cargo metadata"** — Same issue. Ensure `~/.cargo/bin` is in your `PATH`:
```bash
export PATH="$HOME/.cargo/bin:$PATH"
```

**Slow first build** — Normal. Cargo downloads and compiles all Rust dependencies on the first run. Subsequent builds are incremental and much faster.

**Web frontend not loading** — Ensure `web/` dependencies are installed (`cd web && pnpm install`).

## Building

### Development build

```bash
cd macos
pnpm build
```

This produces a debug `.app` bundle. Output location:
```
macos/src-tauri/target/release/bundle/macos/Tank.app
```

### Production build

```bash
cd macos
pnpm build -- --release
```

Produces:
- `src-tauri/target/release/bundle/macos/Tank.app`
- `src-tauri/target/release/bundle/dmg/Tank_0.1.0_aarch64.dmg` (on Apple Silicon)

## Rust Development

### Check compilation

```bash
cd macos/src-tauri
cargo check
```

### Format code

```bash
cd macos/src-tauri
cargo fmt
```

### Lint

```bash
cd macos/src-tauri
cargo clippy
```

### Update Rust dependencies

```bash
cd macos/src-tauri
cargo update
```

## Common Tasks

### Change window size

Edit `macos/src-tauri/tauri.conf.json`:
```json
"windows": [{
  "width": 400,
  "height": 700
}]
```

### Add a Tauri command

1. Add the command function in `src-tauri/src/lib.rs`
2. Register it with `invoke_handler`
3. Call from frontend with `invoke()` from `@tauri-apps/api/core`

### Add a capability/permission

Edit `src-tauri/capabilities/default.json` and add the permission string to the `permissions` array.

### Update app icons

Replace files in `src-tauri/icons/`. Use `pnpm tauri icon <source-image>` to generate all sizes from a single source image.

## Troubleshooting

### "cargo metadata" error

```
failed to run 'cargo metadata' command: No such file or directory (os error 2)
```

Rust is not installed or not in PATH. Fix:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

### WebSocket connection fails in native app

The native app connects to the backend the same way as the browser. Check:
- Backend is running: `curl http://localhost:8000/health`
- No firewall blocking localhost connections

### Window is blank

- Check if web dev server is running: `curl -s http://localhost:5173`
- Check Tauri dev console (right-click → Inspect Element in the native window)

### Build fails with linker errors

Ensure Xcode Command Line Tools are installed:
```bash
xcode-select --install
```
