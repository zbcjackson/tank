# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Required Reading**: At the start of each session, you MUST read the following files:
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and core components
- [CODING_STANDARDS.md](CODING_STANDARDS.md) - Coding standards and design principles
- [TESTING.md](TESTING.md) - Testing guidelines and TDD workflow

## Project Overview

Tank is a voice assistant that supports both Chinese and English, combining speech recognition (OpenAI Whisper), text-to-speech (Edge TTS), and LLM integration for natural conversation. The assistant can execute tools like calculations, weather queries, web searches, and more through function calling.

## Development Commands

### Setup and Installation
```bash
# Install dependencies
uv sync

# Create example configuration
python main.py --create-config
```

### Running the Application
```bash
# Start the voice assistant
python main.py

# Check system status
python main.py --check

# Use custom config file
python main.py --config /path/to/custom/.env
```


