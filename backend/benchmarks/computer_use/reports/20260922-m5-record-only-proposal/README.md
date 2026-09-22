# M5 record-only experiment snapshot

> 状态：2026-09-22，按用户要求停用 benchmark token/费用预算；离线归档，尚未执行模型实验。

Schema v2 proposal selecting record_only=true, with offline preflight evidence.

The user requested actual usage collection before deciding token/cost limits.
Batch execution must pass `record_only=True`. The driver then overrides the agent
budget in memory to zero after comparison verification. Production agent config
is unchanged. Frozen definitions retain their configured budget for provenance.
The 300,000/trial, 5.1M/batch and 8 USD values are historical references, not caps.

Actual provider input/output usage and raw responses remain recorded. Cost is
unpriced (zero monetary placeholders are not actual charges). HTTP failure or
unknown usage stops the batch; insufficient balance must be reported to the user.
Request count, 8,000 output tokens, timeout, steps, input pins and cleanup checks
remain. No paid request or desktop action occurred in this export/preflight.

See the [benchmark guide](../../../README.md#recording-usage-without-tokencost-admission)
for API usage and remaining execution conditions. Old snapshots are unchanged.
