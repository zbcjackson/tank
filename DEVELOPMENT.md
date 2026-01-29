# Development Guide

This document provides development commands and workflows for the Tank Voice Assistant project.

## Package Management

**Tool**: `uv` is the primary package manager.

### Setup and Installation

```bash
# Install dependencies
uv sync

# Create example configuration
uv run python main.py --create-config
```

## Running the Application

```bash
# Start the voice assistant
uv run python main.py

# Check system status
uv run python main.py --check

# Use custom config file
uv run python main.py --config /path/to/custom/.env
```

## Testing

```bash
# Run all tests
uv run python -m pytest tests/

# Run with coverage
uv run python -m pytest tests/ --cov=src/voice_assistant

# Run specific test file
uv run python -m pytest tests/test_tools.py

# Run tests in watch mode during development
uv run python -m pytest tests/ --watch
```

See [TESTING.md](TESTING.md) for comprehensive testing guidelines and TDD workflow.

## Environment Setup

- Always assume `uv` is installed
- Check `.env` for configuration (but don't print secrets)
- `LLM_API_KEY` is critical for functionality
- `SERPER_API_KEY` is optional (enables web search functionality)

## Common Development Tasks

### Fixing Bugs
- Check logs first
- Interruption logic and async race conditions are common sources of issues

### Adding Features
- Follow the TDD pattern: define interface → implement → add tests → register
- See [TESTING.md](TESTING.md) for detailed TDD workflow

## Hardware Dependencies

- Note that `sounddevice` and `whisper` require actual hardware or mocked interfaces in a CI/headless environment
- Be mindful when running code that accesses audio devices
