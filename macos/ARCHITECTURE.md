# macOS App Architecture

This document describes the architecture of the Tank macOS native app.

## Overview

The macOS app is a Tauri 2 native shell that wraps the Tank Web Frontend (`web/`). It provides:
- Native macOS window with overlay title bar
- System-level capabilities (future: global hotkeys, menu bar, notifications)
- Native app bundling (.app / .dmg)

## Technology Stack

- **Framework**: Tauri 2
- **Native Backend**: Rust
- **Frontend**: Reuses `web/` (React 19 + TypeScript + Vite)
- **Build**: Cargo (Rust) + pnpm (JS tooling for Tauri CLI)

## Directory Structure

```
macos/
├── package.json               # pnpm scripts (tauri dev/build)
├── pnpm-lock.yaml
├── .gitignore
└── src-tauri/
    ├── Cargo.toml             # Rust dependencies
    ├── Cargo.lock
    ├── build.rs               # Tauri build script
    ├── tauri.conf.json        # Tauri configuration (window, bundle, build)
    ├── capabilities/
    │   └── default.json       # Permission capabilities for main window
    ├── icons/                 # App icons (macOS, Windows, iOS, Android)
    │   ├── icon.icns          # macOS app icon
    │   ├── icon.ico           # Windows icon
    │   ├── icon.png           # Base icon
    │   └── ...                # Platform-specific sizes
    └── src/
        ├── main.rs            # Entry point (calls lib::run)
        └── lib.rs             # Tauri app builder
```

## How It Works

### Frontend Integration

The macOS app does **not** contain its own frontend. It loads the `web/` sub-project:

```
┌─────────────────────────────────────────┐
│           Tauri Native Shell            │
│  ┌───────────────────────────────────┐  │
│  │        WebView (WKWebView)        │  │
│  │                                   │  │
│  │   web/ React App                  │  │
│  │   ├── VoiceMode                   │  │
│  │   ├── ChatMode                    │  │
│  │   └── WebSocket → Backend         │  │
│  │                                   │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Rust Backend (src-tauri/src/)          │
│  └── Currently: minimal shell          │
│  └── Future: native commands, hotkeys  │
└─────────────────────────────────────────┘
```

### Dev Mode

1. Tauri checks if `http://localhost:5173` is already running
2. If not, starts `pnpm --dir ../web dev` (Vite dev server)
3. Opens a native window pointing at `http://localhost:5173`
4. Hot Module Replacement works — edit `web/src/` and see changes instantly

### Production Build

1. Runs `pnpm --dir ../web build` to produce `web/dist/`
2. Compiles Rust backend
3. Bundles everything into a native `.app` (and optionally `.dmg`)
4. Frontend is served from the embedded `web/dist/` files

## Configuration

### `tauri.conf.json`

| Field | Value | Purpose |
|-------|-------|---------|
| `productName` | "Tank" | App name in menu bar and title |
| `identifier` | "com.tank.voiceassistant" | macOS bundle identifier |
| `build.devUrl` | `http://localhost:5173` | Vite dev server URL |
| `build.frontendDist` | `../../web/dist` | Production frontend path |
| `app.windows[0].titleBarStyle` | "Overlay" | Native macOS overlay title bar |
| `app.windows[0].width/height` | 400 × 700 | Default window size |
| `bundle.macOS.minimumSystemVersion` | "10.15" | Catalina+ required |

### Capabilities (`capabilities/default.json`)

Currently grants `core:default` permissions to the main window. Add more as needed:
- `core:window:allow-close` — window management
- `core:app:allow-version` — app version access
- Custom plugin permissions

## Rust Backend

The Rust side is currently minimal:

```rust
// lib.rs
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running Tank");
}
```

Future additions would go here:
- Custom Tauri commands (invoke from JS via `@tauri-apps/api`)
- System tray / menu bar integration
- Global keyboard shortcuts
- Native file system access
- Auto-update configuration

## Data Flow

```
User interacts with native window
    │
    ▼
WebView renders web/ React app
    │
    ▼
React app connects via WebSocket to Backend (localhost:8000)
    │
    ▼
Same flow as web/ — see web/ARCHITECTURE.md
```

The macOS app adds no additional network layer. The WebSocket connection from the web frontend goes directly to the backend, same as in a browser.
