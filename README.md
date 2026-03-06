# Tank Voice Assistant

Bilingual (Chinese/English) voice assistant with FastAPI backend, Textual CLI, and React web frontend.

## Project Structure

```
tank/
├── backend/              # Backend API server (FastAPI)
│   ├── core/            # Main application
│   ├── contracts/       # Shared ABCs
│   └── plugins/         # TTS plugins
├── cli/                  # Terminal UI client (Textual)
├── web/                  # Web frontend (React)
└── test/                 # E2E tests (Cucumber)
```

## Quick Start

### Backend
```bash
cd backend
uv sync
cd core && uv run tank-backend
```

### Web Frontend
```bash
cd web
pnpm install
pnpm dev
```

### CLI Client
```bash
cd cli
uv sync
uv run tank
```

### Development (tmux)
```bash
./scripts/dev.sh
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall architecture
- [backend/STRUCTURE.md](backend/STRUCTURE.md) - Backend structure
- [backend/core/ARCHITECTURE.md](backend/core/ARCHITECTURE.md) - Backend details
- [cli/ARCHITECTURE.md](cli/ARCHITECTURE.md) - CLI details
- [web/ARCHITECTURE.md](web/ARCHITECTURE.md) - Web details

## Testing

```bash
# Backend tests
cd backend/core && uv run pytest

# Plugin tests
cd backend && uv run pytest plugins/tts-edge/tests/

# E2E tests (requires backend + web running)
cd test && pnpm test
```

## License

MIT
