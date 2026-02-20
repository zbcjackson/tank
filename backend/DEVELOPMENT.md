# Backend Development Guide

This document provides development commands and workflows for the Tank Backend.

## Prerequisites

- Python 3.10+
- uv (package manager)
- Audio device (for local testing)
- LLM API key (OpenAI, OpenRouter, etc.)
- Optional: ffmpeg (for better TTS performance)

## Setup

### Initial Setup

```bash
cd backend

# Install dependencies
uv sync

# Install dev dependencies
uv sync --group dev

# Create configuration
uv run tank-backend --create-config

# Edit .env with your API keys
cp .env.example .env
# Edit .env: add LLM_API_KEY, etc.
```

### Configuration

Edit `backend/.env`:

```env
# Required
LLM_API_KEY=your_api_key_here

# LLM Configuration
LLM_MODEL=anthropic/claude-3-5-nano
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# ASR Configuration
WHISPER_MODEL_SIZE=base
ASR_ENGINE=whisper  # or sherpa

# TTS Configuration
TTS_VOICE_EN=en-US-JennyNeural
TTS_VOICE_ZH=zh-CN-XiaoxiaoNeural

# Audio Configuration
SAMPLE_RATE=16000
CHUNK_SIZE=1600

# Optional: Web Search
SERPER_API_KEY=your_serper_key

# Logging
LOG_LEVEL=INFO
```

## Running the Server

### Development Mode

```bash
# Start server (default: localhost:8000)
uv run tank-backend

# Start with custom config
uv run tank-backend --config /path/to/.env

# Start with debug logging
LOG_LEVEL=DEBUG uv run tank-backend

# Start on custom port
uv run uvicorn tank_backend.main:app --host 0.0.0.0 --port 8080
```

### Check System Status

```bash
# Check configuration and dependencies
uv run tank-backend --check
```

### Production Mode

```bash
# Run with uvicorn directly
uv run uvicorn tank_backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
```

## Testing

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/tank_backend --cov-report=html

# Run specific test file
uv run pytest tests/test_brain.py

# Run specific test
uv run pytest tests/test_brain.py::test_process_input

# Run with verbose output
uv run pytest -v

# Run with debug output
uv run pytest -s
```

### Watch Mode

```bash
# Run tests in watch mode (requires pytest-watch)
uv run ptw
```

### Test Coverage

```bash
# Generate coverage report
uv run pytest --cov=src/tank_backend --cov-report=html

# Open coverage report
open htmlcov/index.html
```

## Development Workflow

### Adding a New Feature

1. **Write tests first** (TDD)
   ```bash
   # Create test file
   touch tests/test_new_feature.py

   # Write failing tests
   uv run pytest tests/test_new_feature.py
   ```

2. **Implement feature**
   ```bash
   # Create implementation file
   touch src/tank_backend/new_feature.py

   # Implement until tests pass
   uv run pytest tests/test_new_feature.py
   ```

3. **Run full test suite**
   ```bash
   uv run pytest
   ```

### Adding a New Tool

1. **Create tool file**
   ```bash
   touch src/tank_backend/tools/my_tool.py
   ```

2. **Implement tool** (inherit from `BaseTool`)
   ```python
   from .base import BaseTool

   class MyTool(BaseTool):
       name = "my_tool"
       description = "Tool description"

       def get_parameters(self) -> dict:
           return {...}

       def execute(self, **kwargs) -> str:
           return result
   ```

3. **Register tool** in `ToolManager`
   ```python
   # In tools/manager.py
   self.register_tool(MyTool())
   ```

4. **Write tests**
   ```bash
   touch tests/test_my_tool.py
   uv run pytest tests/test_my_tool.py
   ```

### Debugging

#### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG uv run tank-backend
```

#### Debug Specific Component

```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
```

#### Interactive Debugging

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use ipdb for better experience
import ipdb; ipdb.set_trace()
```

## Code Quality

### Linting

```bash
# Run ruff (if configured)
uv run ruff check src/

# Auto-fix issues
uv run ruff check --fix src/
```

### Type Checking

```bash
# Run mypy (if configured)
uv run mypy src/tank_backend/
```

### Formatting

```bash
# Format with black (if configured)
uv run black src/ tests/
```

## Common Tasks

### Update Dependencies

```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add package@latest
```

### Add New Dependency

```bash
# Add runtime dependency
uv add package-name

# Add dev dependency
uv add --group dev package-name
```

### Download ASR Models

```bash
# Whisper models are auto-downloaded on first use
# Sherpa models need manual download
cd models/
# Download from sherpa-onnx releases
```

### Test WebSocket Connection

```bash
# Use wscat to test WebSocket
npm install -g wscat
wscat -c ws://localhost:8000/ws

# Send test message
{"type": "text", "content": "hello"}
```

### Test HTTP Endpoints

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>
```

### Audio Device Issues

```bash
# List audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Test audio input
python -c "import sounddevice; sounddevice.rec(16000, samplerate=16000, channels=1)"
```

### Model Loading Issues

```bash
# Check model cache
ls ~/.cache/huggingface/hub/

# Clear cache and re-download
rm -rf ~/.cache/huggingface/hub/
```

### LLM API Issues

```bash
# Test API key
curl -H "Authorization: Bearer $LLM_API_KEY" \
     $LLM_BASE_URL/models

# Check API logs
LOG_LEVEL=DEBUG uv run tank-backend
```

## Performance Profiling

### Profile CPU Usage

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile
await brain.process_input(text)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

### Profile Memory Usage

```bash
# Use memory_profiler
uv add --group dev memory-profiler

# Add @profile decorator to functions
# Run with:
python -m memory_profiler script.py
```

## Deployment

### Docker (Future)

```bash
# Build image
docker build -t tank-backend .

# Run container
docker run -p 8000:8000 \
    -e LLM_API_KEY=$LLM_API_KEY \
    tank-backend
```

### Systemd Service (Linux)

```bash
# Create service file
sudo nano /etc/systemd/system/tank-backend.service

# Enable and start
sudo systemctl enable tank-backend
sudo systemctl start tank-backend
```

## Resources

- FastAPI docs: https://fastapi.tiangolo.com/
- Pydantic docs: https://docs.pydantic.dev/
- pytest docs: https://docs.pytest.org/
- OpenAI API docs: https://platform.openai.com/docs/
