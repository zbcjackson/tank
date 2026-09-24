# M5 archived argument replay

> 状态：2026-09-24，六次拒绝离线重放完成，integrated 工具说明修正；零模型请求、零物理输入。

The six exact argument strings and rejection messages come from the authorized
20260924 A-control trial. The fixture binds the source trace by SHA-256; audit.json
also binds the frozen SDK request used for schema inspection. Historical live
results and freezes have not been rewritten.

Five calls violate the advertised parameter schema: unknown batch screenshot,
string actions, unknown screenshot frame_id, and two string regions. The second
region also contains 1050, outside the documented 0..1000 range; blindly decoding
strings would not make it valid. The sixth call has a valid parameter shape but
follows an invalid screenshot, which clears the current observation. Replaying
that sequence rejects the pointer before native input. Historical frame IDs are
not recreated and no pixel-difference rejection is inferred.

A real description mismatch was found: integrated batch actions advertised
location_id despite requiring frame_id/location. This inherited split-mode text
is now corrected. The appended integrated contract explicitly overrides the old
screenshot batch option, explains JSON arrays, screenshot frame creation, and
re-observation after failed capture. Earlier task-specific instructions remain;
the new contract clarifies their superseded tool format. Split descriptions,
coordinate mapping, validation, defaults and budgets are unchanged.

Regression tests replay each original failure through the actual ToolManager,
IntegratedSession and FrameTool with fake OS/HTTP boundaries. They assert exact
errors and no click/move/event dispatch, then verify fresh observation plus a
legal batch can dispatch. The existing 48 Runner/SDK cases additionally inspect
serialized descriptions and prompt across four protocols, both host-restoration
settings, single/batch and success/truncated/duplicate responses. The description
and prompt regressions failed before each change and pass afterward; the full
file has 146 passing cases.

This proves the deterministic rejection/recovery contract and corrected wire
instructions, not improved model performance. No malformed value is coerced or
silently ignored. Since production source and prompt/schema descriptions changed,
the prior 342-file freeze is stale for future execution. Next regenerate and
review the comparison freeze with the same correction applied to every integrated
variant before any new authorized pilot. The previous live failure remains a
failure; four remaining pilot variants, twelve core trials and phase-transition
orchestration are still pending.

Validation: backend **5010 passed / 1 skipped**; E2E **16 scenarios / 63 steps**.
Web lint/TypeScript, backend/CLI ruff, changed-file pyright, development-server
reload log, documentation and protocol checks passed.
