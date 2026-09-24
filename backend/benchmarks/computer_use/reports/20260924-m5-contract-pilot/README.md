# M5 corrected-contract A-control pilot

> 状态：2026-09-24，获本轮明确授权后执行 1 trial；strict 失败，清理成功，未追加模型运行。

The user approved the corrected-contract single A-control trial with controlled
Calculator/black-background/menu-bar screenshots, including feedback, sent to
https://dashscope.aliyuncs.com/compatible-mode/v1 using
qwen3.7-flash-2026-07-15. The original-size initial screenshot was reviewed before
the go file admitted requests. Code revision 76fb99e used the contract-runtime
freeze and contract-proposal, with at most 16 requests/120 agent seconds/15 steps.

Result: **16 HTTP responses, all 200; 396213 input + 2689 output = 398902 tokens**.
Agent time was 75.33 seconds; full trial time 84.54 seconds. It stopped at 15 tool
steps, without timeout or a spend stop. Token usage exceeded the old 300000
reference by 98902; record-only mode correctly allowed it. No balance error or
unknown usage occurred. Monetary cost remains unpriced; zero ledger dollar fields
do not mean free service. Twelve screenshots were archived; eleven unique hashes
appeared 106 times in HTTP image history.

Strict scoring failed. AX display was 0; independent original-resolution review
of shot_012.png also shows 0, not 56. The final screenshot is a successful zoomed
capture. Business/mouse-only/pixel fields in the raw validator remain unknown;
the separate review does not overwrite them. This is a diagnostic run, not an
estimate of success rate or a controlled proof of prompt improvement.

Observed behavior:

- Both computer_batch calls (turns 2 and 5) accepted JSON arrays and dispatched
  all four clicks; the old unsupported screenshot option did not recur.
  Both zoom requests used arrays and succeeded. This establishes acceptance of
  these calls, not that the model has permanently learned the tool contract.
- The batch repeated locations (853,214), (960,214), (907,214), (960,393).
  Under the frozen 0..1000 full-display contract on a 1920x1080 display, their
  X coordinates map to approximately 1638,1843,1741,1843. These are to the right
  of the Calculator bounds seen in the pre-action image (x=600..1274). The first
  dispatched point is independently logged as Quartz (1638,231). The schema was
  valid but the targets were wrong; this does not establish a host transform bug.
- Turn 8 reused the turn-6 frame after turn 7 created a newer cropped observation;
  it was correctly refused as stale. No pixel-difference refusal occurred.
- Turn 10 supplied key_press with a string containing literal quote characters
  around 7. The key parser rejected that name.
- Turns 12 and 14 supplied location as a JSON-encoded string, not an object;
  both were rejected. There were four top-level tool errors total.
- type_text sent 7*8= at turn 11. Successful dispatch did not produce the required
  result. The trial reports 17 successful primitives, not 17 successful business
  actions; screenshots/launch actions are included by the existing counter.

Automatic cleanup confirmed empty held-key/button state, with no release errors.
External cleanup confirmed Calculator/background closed and clipboard/cursor/
hidden applications restored. The batch finished its sole entry; this does not
mean task success. No other pilot or core run started.

summary.json contains derived usage, exact tool arguments/results and independent
review. live/ preserves original journals, trace, raw SSE bodies, screenshots,
report and cleanup. artifacts.json binds these files and the exact launcher.
Earlier failed pilots and freezes remain unchanged. No production source changed.

Next: prepare the scheduled B-protocol-only pilot using the same corrected freeze,
model and host_restore=false, to test the explicit point protocol. That requires
a bounded entry for the selected pilot plus its own execution authorization;
the current entry only runs A-control. Retain current failures in the comparison,
and do not silently coerce malformed locations or relax frame identity. Four
remaining pilot variants, twelve core trials, phase transition and the final
comparison remain unfinished.

Validation after the trial: backend **5010 passed / 1 skipped**, E2E **16 scenarios /
63 steps**; web lint/TypeScript, backend/CLI ruff, development-server log,
documentation and protocol checks passed. No Python code changed; pyright N/A.
