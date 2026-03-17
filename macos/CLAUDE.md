# CLAUDE.md - macOS App

This file provides guidance to Claude Code when working with the Tank macOS native app.

**Required Reading**: At the start of each session working on macOS app code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - App architecture and Tauri integration
- @CODING_STANDARDS.md [CODING_STANDARDS.md](CODING_STANDARDS.md) - Rust/Tauri coding standards
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - Dev commands and workflows
- @TESTING.md [TESTING.md](TESTING.md) - Testing guidelines

## Project Overview

Tank macOS is a Tauri 2 native wrapper around the Tank Web Frontend. It packages the React/TypeScript web app as a native macOS application with native window chrome, menu bar integration, and system-level capabilities.

## Technology Stack

- **Framework**: Tauri 2
- **Backend**: Rust (thin shell — no custom commands yet)
- **Frontend**: Reuses `web/` (React 19 + TypeScript)
- **Package Manager**: pnpm (JS side) + Cargo (Rust side)

## Key Architecture Decision

This app has **no frontend code of its own**. It loads the `web/` sub-project:
- Dev mode: proxies to `http://localhost:5173` (Vite dev server)
- Production: bundles from `../../web/dist`

All UI changes go in `web/`, not here. This sub-project only handles native platform concerns (window config, Tauri commands, capabilities, bundling).
