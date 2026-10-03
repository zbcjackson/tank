# Frozen model comparison proposal

2026-10-03 — prepared, real batch not yet authorized or run.

- Jev: `jev-1.13.0`, `https://api.typesafe.ai/v1/systemone`, credential environment
  reference `TYPESAFE_API_KEY`.
- Cheap generative comparator: `qwen3.7-flash-2026-07-15`,
  `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`, host
  `computer_use` profile credential. Temperature 0, max output 128, thinking off.
- Both receive the same synthetic semantic evidence per stage; provider-specific
  wrappers differ. Qwen returns a single JSON choice, without tools or self-rated
  confidence. Jev uses its validated distribution/confidence.
- At most 64 requests (32 each), no retries or redirects. Unknown usage or failed
  spend/audit admission stops further model sends; remaining rows stay not-run.
- Shared monetary reservation limit: $0.25. This is a conservative admission
  estimate, not a guarantee about the provider's billing system.
- Jev reservation: 65536 input + 65536 output tokens at $0.042/M input, free output.
- Qwen reservation: official 991808-token input ceiling + enforced 128 output tokens,
  priced at the upper context tier, $0.165/M input and $0.660/M output. This deliberately
  overestimates these short prompts; cache discounts and currency/account billing
  differences are not modeled. Settled reporting uses those same conservative rates.

Sources checked before freezing: [TypeSafe models](https://docs.typesafe.ai/models),
[Alibaba model limits/prices](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-flash),
[thinking mode](https://help.aliyun.com/zh/model-studio/deep-thinking).

From backend, preparation does not load credentials or construct HTTP clients:

```bash
uv run --no-sync python benchmarks/computer_use/s3_replay.py --output <new-directory>
```

After separate approval of the generated digest, run exactly that frozen batch:

```bash
uv run --no-sync python benchmarks/computer_use/s3_replay.py --live \
  --approved-sha256 <approved-digest> --output <prepared-directory>
```

The live CLI verifies the frozen inputs, implementation hashes, endpoint and model
before loading credentials. It refuses an existing spend journal; there is no
implicit resume that could repeat paid requests. Mandatory audit and row journals
are flushed to disk; headers/credentials are not recorded. Raw requests/responses
contain only this synthetic fixture content. A crash can leave incomplete results,
which must be investigated before approving another batch.

Results must distinguish candidate recall, raw and accepted action coverage/wrong
actions, strict control-label accuracy, failed replies and nonexecuted rows, latency
and estimated cost. Inspect individual category rows in addition to stage/arm
summaries. Successful frozen replay still does not prove live task efficiency,
native desktop safety, recovery or production adoption.
