# computer_use benchmark

- Run label: `typing-fidelity-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| typing-fidelity | 0/1 | 0% | 0%–79% | 7 | 7 | 8 | 15 | 26 | 67366 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| typing-fidelity | 8 | 2.0 | 3.1 | 26 | 0.0 |

- API calls total: 8, mean 3.2s/call, median streamed ttft 2.0, LLM time total 26s

## Run metadata

```json
{
  "agent_name": "computer_use",
  "engine": null,
  "extension": null,
  "config": {
    "model": "qwen3.7-flash-2026-07-15"
  },
  "prompt_revision": "929bdb4162b475c28e0212d3c6c200a5af93366c6f0f279066ba245a53f17945",
  "comparison_contract": {
    "variant": "A",
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260924-m6-calc-runtime"
  },
  "input_cleanup": true,
  "budget_record_only": true,
  "agent_budget_enforced": true,
  "configured_token_budget": 300000,
  "spend_budget": {
    "record_only": true,
    "cost_status": "unpriced",
    "batch": {
      "limit_tokens": 300000,
      "limit_nano_usd": 8000000000,
      "charged_tokens": 67366,
      "charged_nano_usd": 0,
      "known_tokens": 67366,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 8
    },
    "trials": {
      "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 67366,
        "charged_nano_usd": 0,
        "known_tokens": 67366,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "d92705e7cd764966a8435156b9d679a4": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5198,
        "output_tokens": 43,
        "status": "known"
      },
      "15a3399bd2c841afae59ffcaa0f6d720": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5272,
        "output_tokens": 13,
        "status": "known"
      },
      "c0743e6a9de04db2a618335bb1cb18d9": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7447,
        "output_tokens": 133,
        "status": "known"
      },
      "b8e5047949ef450395e98381bc55df96": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7627,
        "output_tokens": 229,
        "status": "known"
      },
      "d2b7738e9b574bc5bbafeda5205e97c4": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7978,
        "output_tokens": 44,
        "status": "known"
      },
      "43764a83325e46129ef64620b2614708": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10178,
        "output_tokens": 128,
        "status": "known"
      },
      "b0dc591646bf41b3a8f2685f98ec0e0f": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10353,
        "output_tokens": 41,
        "status": "known"
      },
      "f33358bf7155496f9d4a05fe1bf3835e": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-a/typing-fidelity-r2-a/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12554,
        "output_tokens": 128,
        "status": "known"
      }
    }
  },
  "request_budget": {
    "limits": {
      "planner": 16,
      "locator": 0,
      "total": 16
    },
    "planner": 8,
    "locator": 0,
    "total": 8,
    "blocked": false
  },
  "request_limits": {
    "planner": 16,
    "locator": 0,
    "total": 16
  },
  "grounding": null,
  "token_budget": 300000,
  "platform": "macos",
  "git_revision": "91877d76c39906ffcd486b37f4c077c32d2587af",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "typing-fidelity",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": false,
      "unknown_calls": 0,
      "assessment": {}
    }
  ],
  "limits": [
    {
      "task": "typing-fidelity",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
