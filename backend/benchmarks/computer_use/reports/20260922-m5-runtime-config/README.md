# M5 loadable runtime configuration

> 状态：2026-09-22，离线冻结完成；未执行付费模型或真实桌面对照。

This separate snapshot adds seven loadable configurations under `runtime/`:
A, A-control, B-host-only, B-protocol-only, B-combined, C and D. Each config
resolves its adjacent `agents/computer-use.md`. Historical `original` exists only
in definitions/requests. Previous freeze directories are unchanged.

Credentials are represented solely by `${M5_DASHSCOPE_API_KEY}`. The exporter
round-trips production config/agent parsers and verifies resolved settings before
capturing representative requests with real Runner/SDK and synthetic images.
HTTP transport and desktop boundaries are replaced. The manifest hashes 19
artifacts and the source snapshot; this explanatory README is not an artifact.

Use the explicit `ComparisonContract` described in the
[benchmark guide](../../../README.md) with reviewed `FrozenInputs` pins. The
contract compares definitions, resolved profiles and declared tools before client
construction. It does not validate credentials, billing, full live request
histories, physical cleanup or effectiveness. The 17-trial proposal remains
unexecuted, and the conservative full-context input reservation remains in force.
