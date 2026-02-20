# CLAUDE.md - CLI

This file provides guidance to Claude Code when working with the Tank CLI/TUI Client.

**Required Reading**: At the start of each session working on CLI code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - CLI architecture and components
- @CODING_STANDARDS.md [CODING_STANDARDS.md](CODING_STANDARDS.md) - CLI coding standards
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - CLI development commands
- @TESTING.md [TESTING.md](TESTING.md) - CLI testing guidelines

## Project Overview

Tank CLI is a terminal-based client for the Tank Voice Assistant backend. It provides:
- Textual-based TUI (Terminal User Interface)
- Local audio capture via microphone
- Audio playback via speaker
- WebSocket client for real-time backend communication

## Technology Stack

- **Framework**: Textual (TUI)
- **Language**: Python 3.10+
- **Package Manager**: uv
- **Audio**: sounddevice, pydub, silero-vad
- **WebSocket**: websockets
