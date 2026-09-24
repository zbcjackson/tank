# M5 refreshed runtime freeze

> 状态：2026-09-24，七组 runtime 与代表性 SDK 请求已离线冻结；无真实模型请求。

Generated from the current production configuration with the existing offline
exporter. The freeze includes the paste release fix, removal of pixel-equality
admission, and native input cleanup support. A, A-control, B-host-only,
B-protocol-only, B-combined, C and D keep their previous model/protocol factors.
Credentials are environment references; the exported SDK exchanges use synthetic
images and a fake HTTP transport. No desktop input or external request occurred.
Old freezes and the failed A-control trial remain immutable.

See ../20260924-m5-proposal for the refreshed 17-trial proposal and
../20260924-m5-pilot-ready for the single A-control review/preview. This export
alone does not authorize a live run or establish model effectiveness.

Validation: backend **5004 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, changed-file pyright, running backend log,
docs and protocol synchronization passed. Entry implementation: `92070ff`.
