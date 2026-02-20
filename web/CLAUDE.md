# CLAUDE.md - Web Frontend

This file provides guidance to Claude Code when working with the Tank Web Frontend.

**Required Reading**: At the start of each session working on web frontend code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - Frontend architecture and data flow
- @CODING_STANDARDS.md [CODING_STANDARDS.md](CODING_STANDARDS.md) - TypeScript/React coding standards
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - Dev commands and workflows
- @TESTING.md [TESTING.md](TESTING.md) - Frontend testing guidelines

## Project Overview

Tank Web is a React/TypeScript SPA providing a browser-based interface for the Tank Voice Assistant. It streams audio to the backend via WebSocket and plays back TTS audio using the Web Audio API.

## Technology Stack

- **Framework**: React 19 + TypeScript
- **Build**: Vite
- **Styling**: Tailwind CSS v4
- **Animation**: Framer Motion
- **Package Manager**: npm
