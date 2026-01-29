# GEMINI.md

This file provides specific context and instructions for the Gemini agent working on the Tank Voice Assistant project.

**Required Reading**: At the start of each session, you MUST read the following files:
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and core components
- [CODING_STANDARDS.md](CODING_STANDARDS.md) - Coding standards and design principles
- [TESTING.md](TESTING.md) - Testing guidelines and TDD workflow

## Development Guidelines

### Package Management
- **Tool**: `uv` is the primary package manager.
- **Commands**:
    - Install dependencies: `uv sync`
    - Run tests: `uv run python -m pytest tests/`
    - Run app: `uv run python main.py` (or just `python main.py` if venv is active)


## Context for Gemini

1.  **Environment Setup**:
    - Always assume `uv` is installed.
    - Check `.env` for configuration (but don't print secrets).
    - `LLM_API_KEY` is critical for functionality.

2.  **Common Tasks**:
    - **Fixing Bugs**: Check logs first. Interruption logic and async race conditions are common sources of issues.
    - **Adding Features**: Follow the pattern: define interface -> implement -> add tests -> register.

3.  **Hardware Dependencies**:
    - Note that `sounddevice` and `whisper` require actual hardware or mocked interfaces in a CI/headless environment. Be mindful when running code that accesses audio devices.
