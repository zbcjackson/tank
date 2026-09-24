# M5 tool-contract runtime freeze

> 状态：2026-09-24，工具说明修正后的七组 runtime 与代表性 SDK 请求已离线冻结；零模型请求/桌面操作。

Generated with prepare_computer_comparison.py from core/config.yaml at fa4a954,
including the 0d14277 integrated tool-contract correction. Current source and
runtime artifacts are hash-bound. Credentials remain environment references.
Synthetic images and fake HTTP/OS boundaries generate the representative SDK
requests; these are not live model results.

Compared with 20260924-m5-runtime, A, C, D and the original request are identical.
Only system instructions and tool descriptions differ for A-control and the three
B variants. After excluding descriptions, tool schemas match; all other request
fields and non-system messages match. Models, generation parameters, coordinate
factors and image identities are unchanged. See
../20260924-m5-contract-ready/request-diff.json for the checked variant inventory.
Historical freezes are preserved; future execution must use this refreshed set.

Validation: backend **5010 passed / 1 skipped**, E2E **16 scenarios / 63 steps**;
web lint/TypeScript, backend/CLI ruff, development-server log, docs and protocol
checks passed. No production Python changed; changed-file pyright N/A.
