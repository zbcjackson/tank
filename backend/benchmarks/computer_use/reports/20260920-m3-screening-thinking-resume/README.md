# M3 thinking continuation after balance recovery — 2026-09-20

This continuation retains the original interrupted batch and its HTTP 402. The
user reported that DeepSeek balance was restored. A new frozen batch schedules
25 previously unsent requests plus one explicit repeat of the failed DeepSeek
off request. No completed response is rerun. This is a resumption after an
external state change, not an automatic retry hidden in one attempt.

## Frozen scope and accounting

The [manifest](manifest.json) carries forward 47 screening requests and 91012
known tokens. The old 402 still has unknown usage. Its entire original reservation
(10000 estimated input + 16000 maximum output = **26000 tokens**) is held against
the shared 1000000-token cap. This conservative treatment permits continuation
without claiming the failed request was free or that its usage was recovered.
The input allowance is an estimate, not an exact tokenizer bound. Before each
call the driver checks known usage + the old reservation + the next reservation;
a new API failure, timeout, missing usage or excess input stops the batch.

[Driver](runner.txt) and [offline checks](offline-check.json) freeze all 26 requests
through the production adapter, LLM and SDK. Every serialized body equals its
counterpart in the original manifest; both arms retain point/integer/found,
`detail=auto`, no strict flag, temperature 0.1 and 16000 output tokens. Only the
provider's thinking switch differs in each pair. Source and prior-record hashes
are checked before live dispatch. Four PNGs are identical to the originals and
remain disjoint from the reserved holdout images. The original six completed
Qwen responses are reused without regrading or selecting favorable outcomes.

DeepSeek's documented thinking mode ignores temperature and uses default high
effort; the comparison is between service modes, not a pure internal reasoning
intervention. The new off/on DeepSeek pair is adjacent after restoration, but
an account-recovery gap separates the two batches. Planned pair ordering remains
two off-first / two on-first layouts per model; model order is fixed and rotated,
not randomized. There is only one response per layout and setting.

The new 26-call estimate is $0.807588 at uncached peak list rates. DeepSeek
[pricing](https://api-docs.deepseek.com/quick_start/pricing/) was successfully
rechecked before continuation: Flash input/output $0.30/$1.20 per million.
[Qwen Max](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max) remains
$1.65/$4.951 for the Beijing snapshot. Same-day Qwen Flash price evidence and
thinking contracts remain linked in the original report. These are estimates,
not provider billing statements. Original raw results and unknown usage remain
unchanged, even after operational recovery.

## Completed results and decision

All **26 continuation requests returned HTTP 200 with known usage**. Combined
with the six original completed responses, all 32 grid settings are populated.
The original 402 remains a 33rd attempt, never overwritten or reclassified.
Off/on completed-grid hits and legal-output counts (four responses per setting):

- Qwen3.7: hits 3/4 versus 0/4; both legal 4/4.
- Qwen3.8 Flash: hits 0/4 versus 4/4; legal 0/4 versus 4/4.
- Qwen3.8 Max: hits 4/4 versus 3/4; both legal 4/4.
- DeepSeek: hits 2/4 versus 3/4; legal 3/4 versus 4/4.

Including the original account failure, DeepSeek off has five attempts, three
legal outputs and two hits (2/5), not 2/4. Overall, all attempts yield 27/33 legal
outputs and 19/33 hits; the completed-response grid is 27/32 legal and 19/32 hits.
Four Flash-off replies return arrays. One DeepSeek-off HTTP 200 reply omits the
required function call; it stays a format failure, not a repaired text answer.
All 32 completed responses avoid truncation; all 16 thinking-on replies contain
reasoning content and provider reasoning-token counts. Off replies omit that count,
so known zero aggregates are not interpreted as explicit provider-reported zeros.

Qwen3.8 Flash thinking-on is now a candidate worth further validation, not an
adoption decision. This setting had four valid hits where its paired off setting
had none. Thinking does not generally improve grounding: Qwen3.7 on missed every
target, and Max on included a 189.882-pixel miss. Max's off result does not prove
that increasing the budget fixed the earlier malformed output; that was not the
within-pair intervention. Retain strict parsing and the production baseline.
Next isolate image/detail and explicit absent/ambiguous status behavior, then
freeze selected configurations before holdout. Native protocols remain unverified.

Continuation known usage is **59602 tokens**; combined thinking known usage is
71257 plus the original unknown call. Screening is now **73/144 requests** and
**150614 known tokens + 26000 reserved**. Conservative accounted usage is 176614,
leaving **71 request slots / 823386 tokens after reservation**. The old call's
actual usage is still unknown; the reservation is not reported as consumption.
Preflight remains 16/16 requests and 26398 tokens.

Continuation actual-usage uncached peak list-price estimate is $0.042842553;
combined known thinking responses estimate $0.050606745. No provider reports billed
cost, and the original failed call remains unknown, so actual total billing is
unknown. Restoration is evidenced by eight new DeepSeek HTTP 200 responses and
successful runtime revalidation, not by modifying the historical failure record.

## Evidence and limitations

[Results](results.json) retain each new request, response, arguments and usage.
[Combined summary](summary.json) reports every attempt from both batches, including
the original 402, separately from the completed off/on grid. [Offline audit](offline-replay.json)
replays original and new artifacts; [audit driver](replay.txt) checks frozen HTTP
bodies, PNG hashes, parsed completions, failures and rounded-button hit scores.
Malformed coordinates and truncations stay failures; no unit guessing or
coordinate repair is performed. Pixel error is reported only for legal locations,
not substituted for full-denominator hit counts. No native bbox capability or
absent/ambiguous handling is established by this point-only test.

Default models, production adapter and desktop behavior are unchanged. There are
no real screenshots, desktop actions or holdout calls. Four development layouts
cannot establish reliability or justify adoption. Timing includes local capture
and concurrent regression tests, so it is not a latency comparison.

## Tests

Before live execution, shared grounding suite: 83 passed; 26 fake SDK requests
matched the original frozen bodies; all 16 combined pairs differ only in their
thinking switch. Full verification is recorded in [verification.json](verification.json).
Backend 4595 passed / 1 skipped; E2E 14 scenarios / 55 steps passed. Web lint
and TypeScript, backend/CLI lint, docs and protocol checks passed. The real
backend pane has no error/traceback/exception matches after E2E; the historical
402 remains in the original record. All 33 original/new attempts replayed
successfully, including the original error.
No Python source or tests changed; changed-file pyright is N/A. Text drivers are
execution records, not new production tools or supported CLIs.
