# tank_protocol

Single source of truth for the Tank client WebSocket wire contract.
Backend (`tank_backend`) and CLI (`tank-cli`) import it directly; the web
frontend and device firmware consume generated artifacts that are derived
from this package (see "Codegen" below).

## Contents

| Module | Purpose |
|---|---|
| `enums` | `MessageType` — the 8 wire message types |
| `envelope` | `WebsocketMessage` / `WebsocketAttachment` — the wire envelope (all 9 fields serialized on every frame, `null` explicit) |
| `payloads` | Per-type legal envelope-field sets + known metadata keys + `validate_envelope()` (advisory warnings; the wire itself stays lenient) |
| `factories` | Constructor factories — the one sanctioned way to build outbound frames |
| `schema` | JSON Schema export + codegen entry point (`python -m tank_protocol.schema`) |

Dependencies: `pydantic` only. No backend-internal imports.

## Evolution rules

1. **Additive-only.** New message types / fields / signal names are allowed.
   Changing the meaning of or removing an existing field requires a protocol
   major version bump (and a migration note for each client).
2. **Unknown must be ignored.** Clients receiving an unknown message type,
   signal name, or field must warn and ignore — this is contract, not
   courtesy. Servers do the same for unknown client types.
3. **`metadata` keys are documented here.** Every new key goes into
   `payloads.METADATA_KEYS` (and thus the JSON Schema); no more keys that
   only one side understands.
4. **Generated artifacts must stay in sync.**
   `scripts/check_protocol_sync.py` regenerates
   `schema/tank_protocol.schema.json`,
   `device/test/test_native/test_ws_message/golden_frames.h`, and
   `web/src/types/protocol.ts` and fails on any diff. A version bump in
   `pyproject.toml` without regenerating is a broken build.

## Codegen

```bash
# Regenerate all committed artifacts (from repo root):
cd backend && uv run python -m tank_protocol.schema \
    --schema-out contracts/tank_protocol/schema/tank_protocol.schema.json \
    --golden-out ../device/test/test_native/test_ws_message/golden_frames.h
cd ../web && pnpm generate:protocol   # schema -> src/types/protocol.ts
python3 scripts/check_protocol_sync.py   # verify no drift
```

## Consumers

| Client | How it consumes |
|---|---|
| `backend/core` | uv workspace dependency, direct import; all outbound frames built via `factories` |
| `cli` | uv path dependency (editable); the hand-copied `tank_cli/schemas.py` was deleted |
| `web` | `web/src/types/protocol.ts`, generated from `schema/tank_protocol.schema.json` via `json-schema-to-typescript` |
| `device` | `golden_frames.h` — one real wire frame per message type, asserted against the C++ parser in the native test suite (no code sharing) |
