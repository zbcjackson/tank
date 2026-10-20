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

LLM profiles accept explicit `temperature: null` to omit the parameter from
streaming and non-streaming requests, for models/routes that reject sampling
controls. Omitting the YAML key retains the existing default of 0.7; an explicit
numeric per-call override still takes precedence. This is required by the tested
OpenRouter → OpenAI GPT-5.5 route with `require_parameters: true`.

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

# Agent orchestration — single agent with all tools.
agents:
  chat:
    type: chat
    llm_profile: default

# Approval policies — control which tools require user confirmation.
approval_policies:
  always_approve:
    - get_weather
    - get_time
    - calculate
  require_approval:
    - run_command
    - persistent_shell
    - manage_process
  require_approval_first_time:
    - web_search
    - web_fetch

# Unified database — one SQLAlchemy/ORM-backed DB for conversations,
# channels, jobs, and speakers. Alembic auto-migrates at startup.
# Swap to Postgres by changing ``url`` to a postgresql+psycopg DSN.
database:
  url: sqlite+pysqlite:///~/.tank/tank.db
  echo: false

# Context — conversation history compaction. Turn persistence uses the
# unified database above.
context:
  persist: true

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
# Set false and restart the backend to disable tracing without removing keys.
LANGFUSE_TRACING_ENABLED=true

# Logging
LOG_LEVEL=INFO
```

When using `http://localhost:3001`, start the Langfuse services from the repository
root with `docker compose up -d`. If tracing is not needed for a test, set
`LANGFUSE_TRACING_ENABLED=false` and restart the backend. A configured but
unavailable Langfuse service produces trace export and media upload errors.

### Core decision models

Core manages Jev through the official TypeSafe SDK. `core/config.yaml` includes
an opt-in `decision_models.jev` profile; add `TYPESAFE_API_KEY` to `core/.env` when
using it. An extension agent references it with `decision-model: jev`; ordinary
text `model:` references still select `llm` profiles. A configured profile alone
never invokes the provider and does not change the default agent.

For a custom host config:

```yaml
decision_models:
  jev:
    url: https://api.typesafe.ai/v1/systemone
    model: jev-1.13.0
    credential_env: TYPESAFE_API_KEY
```

Old `json_models` / `json-model` fields are rejected with migration guidance.
Replace them with `decision_models` / `decision-model`, removing the old profile's
`extension` or `provider` field. There is one decision implementation (Jev), so no
provider selector or provider plugin is required. Core owns SDK resources; task
wrappers account usage. Runtime-API declarations must be 3 for the SDK-call contract.
Callers submit bounded decisions; they never configure HTTP transports.

SDK 0.7.5 adds offline image/Box capability preparation. An experimental host
config can declare a separate Jev profile with `images: true`, an explicit
supported version (`jev-1.14.0` for Box), URL and credential reference. This
recipient opt-in allows task image scope; callers may still narrow it to text.
Existing profiles default to `images: false`; `TaskModel` and ordinary
`DecisionModel.choose` remain text/JSON-only. Task `choose_image`/`locate_image`
share original accounting/deadlines. Plugin `JevImageProbe` is read-only, with no
executor or production factory mode. No production config is changed. See the
[development recipe](benchmarks/computer_use/fixtures/jev-image-dev/README.md).
The separate `benchmarks.computer_use.jev_image_eval` CLI prepares five-arm frozen
request previews offline and supports explicit digest-gated, read-only model runs.
It retains independent scores, known/unknown usage and all planned rows on stops;
preparation and regression tests never make paid requests. See the recipe's
read-only executable comparison for limits and execution instructions.
The visual service additionally exposes `complete_json(messages)` to request
JSON-object output using the same task admission, capture, accounting and cleanup
as `complete`. It returns the raw text; callers validate its fields and semantics.
The revision-2 image evaluator uses this mode and explicitly converts declared
0–1000 `bbox_2d` edges into normalized coordinates, without guessing or repairing
provider output. Existing plain completions do not enable JSON mode.
Experimental `selector: jev-image` and optional bounded `advisor: jev-image` use the
image-enabled decision profile directly, without a separate visual LLM. Only finite
bound actions are executable; Box remains read-only. The new real-application
[Calculator recipe](benchmarks/computer_use/fixtures/jev-image-native/README.md)
prepares offline and supports separately frozen fake-model or live-model runs on
new owned Calculator windows. Fake-model real-app runs are functional verification,
not model-quality evidence.
The separate [TextEdit ablation](benchmarks/computer_use/fixtures/jev-image-ablation/README.md)
compares one-decision text/image replacements on temporary colored RTF documents.
It preserves actual AX evidence and original native gates, keeps private completion
out of both model projections, and separates model choice, native completion and
read-only Box calibration. Its benchmark-only selector is not a production factory mode.
The separate `benchmarks.computer_use.jev_box_crop` comparison reuses saved experiment
request PNGs and same-request AX labels, with full-window/region representations and
Jev/Gemini profiles. Prepare with `--output`, `--textedit`, `--calculator` source-run
directories and `--catalog` (saved OpenRouter model catalog JSON); execute with only
`--output --run --approved-sha256`. Live keys come from TYPESAFE_API_KEY and
OPENROUTER_API_KEY. It has no desktop grant/executor, uses record-only accounting,
and preserves six control plus 64 main rows on failure. See the
[comparison plan](../docs/plans/done/jev-box-crop-comparison.md).

`benchmarks.computer_use.jev_vision_route` prepares new synthetic HTML tasks offline
with `--output`; `--output --run --approved-sha256` runs the frozen V/JT comparison
in isolated Chromium, using TYPESAFE_API_KEY and OPENROUTER_API_KEY. The V policy
exists only in this benchmark; JT reuses `jev-vision`. Both use the same visual
JSON-object choice contract, rules, action checks and independent page readback.
The 24 planned rows include positive multi-step work and three negative families;
known model misses remain in the denominator, unknown usage or cleanup stops the
batch. See the [route pilot](../docs/plans/done/jev-vision-route-pilot.md).

Use preparation flag `--followup` for the repaired 36-task extension: the original
24 tasks plus uniquely named neutral palette controls with unavailable text color
semantics. Execution still accepts only the frozen directory/digest. It does not
force Jev to abstain. `goal_completed` records physical goal/path/cleanup; new JT
semantic-gap tasks additionally require observed text control then same-binding
visual fallback and no unsupported palette candidate for `strict_completed` (or
negative acceptance). All guesses and original goal outcomes remain visible. See
[the follow-up plan](../docs/plans/done/jev-vision-route-followup.md).

The managed DOM channel uses one `visual_png` policy for evidence and rechecks.
Ordinary same-origin, same-window links can declare an exact destination effect
through the host-owned `status:Page URL` fact; downloads, external/new-window and
malformed destinations are excluded. A blocked navigation stays effect-unknown.
Uniquely named native checkboxes use actual checked-state readback, not a click
receipt. These are local effects; task completion still requires its own evidence.
Loading documents are incomplete observations. Image capture waits at most 250ms
for active Web Animations to settle, then refuses continuing motion; it does not
disable animations or relax the exact PNG comparison at dispatch.
It suppresses native carets through a persistent constructable stylesheet, leaving
DOM attributes/revisions intact. It still compares exact PNG hashes and retains
DOM-object, navigation, actionability and authority checks. Freshness refusals emit
`computer_use_freshness` metadata (stage/observation/action and image hashes where
applicable); these events contain no PNG or page body. The no-model
`benchmarks.computer_use.dom_visual_freshness --output <new-directory>` records
actual check PNGs, native-caret/hide controls, DOM equality and owned-browser cleanup.
Its focus/seed setup precedes observation; it never dispatches task inputs or loads
model credentials. See the [diagnosis plan](../docs/plans/done/dom-visual-freshness.md).

Experimental Computer Use `selector: jev-vision` additionally requires an explicit
extension-agent `visual-model: <llm-profile>` declaration. It permits screenshots
to that named profile. Its visual choices request JSON-object mode and still
validate the exact choice contract. `model:` remains a text-only service and Jev still
receives text Choice questions. A caller may narrow the task's image allowance;
without image scope the visual path stops before capture. No production profile
or default is changed. See the plugin README for the finite-candidate and
main-frame/native-window limits and fake-model test boundary.

`DecisionModel` can also be used by a core caller without a task context. Its
`choose(state=..., instructions=..., options=...)` returns `ChoiceResult` including
choice, confidence, probabilities and optional input/output token counts. A
`TaskDecisionModel` borrows that service and adds task cancellation/deadline and
ledger recording; the creator owns SDK cleanup. Existing optional Langfuse settings
apply to model spans; tracing is not required for successful model execution.

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


### Jev HTTP defaults

Jev uses the official SDK's own HTTP client. Tank passes a 30-second SDK timeout and
zero retries and explicit `compression=False`, without injecting HTTP clients.
SDK 0.7.5 may otherwise use zstd when available; services freeze uncompressed
serialization and tests inspect the SDK default separately. Environment proxy and
certificate settings now follow SDK defaults (`trust_env=True` in the pinned HTTP
library), replacing the earlier explicit opt-out. The current library default does
not follow redirects. Other model/replay client settings are unchanged.

For the real-product development comparison, install `sqlite-web==0.8.1` into a
separate temporary venv, then prepare with
`uv run --no-sync python -m benchmarks.computer_use.jev_real_product_route --output <new-dir> --app-python /absolute/venv/bin/python`.
Execute only after verification/review using `--output <dir> --run --approved-sha256 <digest>`.
Preparation freezes the app environment's source/assets/metadata and Python bytes,
SDK versions, host source and all 12 tasks without creating clients or servers.
Each task starts its own upstream app and synthetic database on loopback; an
external WSGI boundary may reject the first form GET once with an explicit Retry
link. No product HTML/source is changed. Both conditions start on actual forms;
list navigation/record discovery and open planning are not measured. The benchmark
adds actual read-only database rows to the same observation in both arms, while a
separate final schema/write audit checks full business state. See
[the completed plan](../docs/plans/done/jev-real-product-route.md).
