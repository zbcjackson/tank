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

Edit `backend/.env` for secrets:

```env
# Required — referenced by core/config.yaml via ${LLM_API_KEY}
LLM_API_KEY=your_api_key_here

# Optional: Web Search
SERPER_API_KEY=your_serper_key

# Logging
LOG_LEVEL=INFO
```

Edit `backend/core/config.yaml` for LLM profiles, agents, and pipeline settings:

```yaml
# LLM profiles — named configurations for different providers/models.
# Use ${VAR} syntax to reference environment variables.
llm:
  default:
    api_key: ${LLM_API_KEY}
    model: openai/gpt-oss-120b
    base_url: https://openrouter.ai/api/v1
    temperature: 0.7
    max_tokens: 10000
    extra_headers:
      HTTP-Referer: "http://localhost:3000"
      X-Title: "Tank Voice Assistant"
    stream_options: true
  # Optional: cheaper model for context summarization
  # summarization:
  #   api_key: ${LLM_API_KEY}
  #   model: openai/gpt-4o-mini
  #   base_url: https://openrouter.ai/api/v1
  #   temperature: 0.3
  #   stream_options: false

# Echo guard — defense against assistant hearing itself through speakers.
echo_guard:
  enabled: true
  vad_threshold_during_playback: 0.85  # higher = less sensitive during playback
  self_echo_detection:
    similarity_threshold: 0.6          # discard if >60% token overlap
    window_seconds: 10.0               # compare against last 10s of TTS text

# Plugin slot assignments
asr:
  enabled: true
  extension: asr-sherpa:asr
  config:
    model_dir: ../models/sherpa-onnx-zipformer-en-zh
    num_threads: 4
    sample_rate: 16000

tts:
  enabled: true
  extension: tts-edge:tts
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural

# Brain — conversation processing
brain:
  max_history_tokens: 8000             # auto-summarize when exceeded

# Agent orchestration — route user messages to specialized agents.
# Remove this section entirely to use the default direct-LLM path.
agents:
  chat:
    type: chat
    llm_profile: default
  search:
    type: search
    llm_profile: default
    tools: [web_search, web_scraper]
  task:
    type: task
    llm_profile: default
    tools: [calculate, get_time, get_weather]
  code:
    type: code
    llm_profile: default
    tools: [sandbox_exec, sandbox_bash, sandbox_process]

# Router — intent classification for agent dispatch.
router:
  llm_profile: default                 # enables LLM-based slow-path classification
  default: chat
  routes:
    search:
      agent: search
      keywords: [search, look up, find, google, 搜索, 查找, 查一下]
      description: Web search and information retrieval
    code:
      agent: code
      keywords: [run code, execute, python, script, 运行代码, 执行]
      description: Code execution in sandbox
    task:
      agent: task
      keywords: [calculate, compute, what time, 计算, 几点, 天气]
      description: Calculations, time queries, and weather

# Approval policies — control which tools require user confirmation.
approval_policies:
  always_approve:
    - get_weather
    - get_time
    - calculate
  require_approval:
    - sandbox_exec
    - sandbox_bash
    - sandbox_process
  require_approval_first_time:
    - web_search
    - web_scraper

# Conversation persistence — save/restore history across restarts.
persistence:
  enabled: false
  db_path: ../data/sessions.db

# Sandbox — Docker container for code execution tools
sandbox:
  enabled: true
  image: tank-sandbox:latest
  workspace_host_path: ./workspace
  memory_limit: 1g
  cpu_count: 2
  default_timeout: 120
  max_timeout: 600
  network_enabled: true
```

Optional observability settings in `.env`:

```env
# Langfuse LLM tracing (optional — set all three to enable)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3001

# Logging
LOG_LEVEL=INFO
```

## Running the Server

### Development Mode

```bash
# Start server (default: localhost:8000)
uv run tank-backend

# Start with auto-reload (recommended for development)
uv run tank-backend --reload

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

### Adding a New Agent

1. **Create agent file** in `src/tank_backend/agents/`
   ```python
   from .chat_agent import ChatAgent

   class MyAgent(ChatAgent):
       """Specialized agent for my domain."""

       def __init__(self, llm, tool_manager, approval_manager=None):
           super().__init__(llm, tool_manager, approval_manager)
           self.name = "my_agent"
           self.system_prompt = "You are a specialized assistant for..."
   ```

2. **Register in factory** (`agents/factory.py`)
   ```python
   def create_agent(agent_type: str, ...) -> Agent:
       if agent_type == "my_domain":
           return MyAgent(llm, tool_manager, approval_manager)
   ```

3. **Add to config.yaml**
   ```yaml
   agents:
     my_domain:
       type: my_domain
       llm_profile: default
       tools: [tool_a, tool_b]

   router:
     routes:
       my_domain:
         agent: my_domain
         keywords: [keyword1, keyword2, 关键词]
         description: What this agent handles
   ```

4. **Set approval policy** (optional)
   ```yaml
   approval_policies:
     require_approval:
       - tool_a
   ```

### Adding a New Pipeline Processor

1. **Create processor file** in `src/tank_backend/pipeline/processors/`
   ```python
   from ..processor import Processor, FlowReturn

   class MyProcessor(Processor):
       name = "my_processor"

       async def process(self, item):
           result = transform(item)
           yield FlowReturn.OK, result
   ```

2. **Wire into pipeline** via `PipelineBuilder` in the Assistant initialization

3. **Write tests** — test `process()` in isolation with mock inputs

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
# Check for lint errors
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/
```

### Formatting

```bash
# Format code
uv run ruff format src/ tests/

# Check formatting without changing files
uv run ruff format --check src/ tests/
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
cd backend
uv run python scripts/download_models.py
```

### Speaker Identification

#### Enable Speaker ID

```bash
# In backend/.env, enable the toggle:
ENABLE_SPEAKER_ID=true
```

Speaker plugin settings live in `backend/core/config.yaml`:

```yaml
speaker:
  plugin: speaker-sherpa
  config:
    model_path: ../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
    num_threads: 1
    provider: cpu
    db_path: ../data/speakers.db
    threshold: 0.6
    default_user: Unknown
```

#### Download Speaker Model

```bash
# Download the speaker embedding model
uv run python scripts/download_models.py
```

#### Record Audio for Testing

```bash
# Record 5 seconds of audio
uv run python scripts/record_audio.py ../data/my_voice.npy --duration 5

# Record with custom sample rate
uv run python scripts/record_audio.py ../data/my_voice.npy --duration 3 --sample-rate 16000
```

#### Manage Speakers

```bash
# List all enrolled speakers
uv run python scripts/manage_speakers.py list

# Enroll a speaker (single audio sample)
uv run python scripts/manage_speakers.py enroll user123 "John Doe" ../data/john_voice.npy

# Enroll with multiple samples (improves accuracy)
uv run python scripts/manage_speakers.py enroll user123 "John Doe" \
    ../data/john_sample1.npy \
    ../data/john_sample2.npy \
    ../data/john_sample3.npy

# Test speaker identification
uv run python scripts/manage_speakers.py test ../data/test_voice.npy

# Delete a speaker
uv run python scripts/manage_speakers.py delete user123

# Export speaker database to JSON
uv run python scripts/manage_speakers.py export speakers_backup.json

# Import speaker database from JSON
uv run python scripts/manage_speakers.py import speakers_backup.json

# Use custom database path
uv run python scripts/manage_speakers.py --db /path/to/speakers.db list
```

#### Test Speaker ID via REST API

```bash
# List enrolled speakers
curl http://localhost:8000/api/speakers

# Enroll a speaker (requires audio file)
curl -X POST "http://localhost:8000/api/speakers/enroll?name=Jackson" \
    -F "audio=@../data/jackson_voice.npy"

# Delete a speaker
curl -X DELETE http://localhost:8000/api/speakers/user123
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
# Health check (simple)
curl http://localhost:8000/health

# Health check (detailed — shows pipeline, queue, processor status)
curl http://localhost:8000/health?detail=true

# Pipeline metrics
curl http://localhost:8000/api/metrics

# Per-session metrics
curl http://localhost:8000/api/metrics/{session_id}

# List pending tool approvals
curl http://localhost:8000/api/approvals

# Approve a tool execution
curl -X POST http://localhost:8000/api/approvals/{id}/respond \
    -H "Content-Type: application/json" \
    -d '{"approved": true}'

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
