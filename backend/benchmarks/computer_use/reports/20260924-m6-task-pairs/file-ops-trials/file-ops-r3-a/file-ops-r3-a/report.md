# computer_use benchmark

- Run label: `file-ops-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| file-ops | 0/1 | 0% | 0%–79% | 15 | 14 | 16 | 15 | 41 | 189642 | 6 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| file-ops | 16 | 1.5 | 2.4 | 41 | 0.0 |

- API calls total: 16, mean 2.6s/call, median streamed ttft 1.5, LLM time total 41s

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
      "charged_tokens": 189642,
      "charged_nano_usd": 0,
      "known_tokens": 189642,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 189642,
        "charged_nano_usd": 0,
        "known_tokens": 189642,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "d1bd3cdb098e48c1bcd278699e2e5de2": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5124,
        "output_tokens": 108,
        "status": "known"
      },
      "a050a16bb6584a208f1141117b31c127": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5262,
        "output_tokens": 13,
        "status": "known"
      },
      "a3ead36e101f4b1fa3eb67cc081872e4": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7437,
        "output_tokens": 75,
        "status": "known"
      },
      "03dbae95546a4cf39427daaaa92453f2": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7415,
        "output_tokens": 31,
        "status": "known"
      },
      "57e997aca0aa4acbad7821eb2d790eb4": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7469,
        "output_tokens": 28,
        "status": "known"
      },
      "a7845180cf8843ac836c80a734ed5771": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9653,
        "output_tokens": 81,
        "status": "known"
      },
      "9f3121380dd844fcb8c1a6f4a60de9fd": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9754,
        "output_tokens": 14,
        "status": "known"
      },
      "022baf829fda459fac2d6005d3b68e9d": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11928,
        "output_tokens": 103,
        "status": "known"
      },
      "7c5d083763b44aa6a22949faca9be39b": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12079,
        "output_tokens": 72,
        "status": "known"
      },
      "bb875c4492bc487ca1aafca2daf5a57c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12199,
        "output_tokens": 25,
        "status": "known"
      },
      "5d5b90b77c61423eb3d0595e9923b05c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14380,
        "output_tokens": 62,
        "status": "known"
      },
      "3f5efdd6b25a4b3dbac697a03ef6094c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14490,
        "output_tokens": 30,
        "status": "known"
      },
      "eb5d74059ccd4ff19ecdd81a0a5c13a8": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16680,
        "output_tokens": 96,
        "status": "known"
      },
      "dd427d14ca5242ab86a8ac8f379ec818": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16824,
        "output_tokens": 14,
        "status": "known"
      },
      "ebba0239953f4a6cb64b1af830a00be5": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18998,
        "output_tokens": 61,
        "status": "known"
      },
      "5b6ade52b9df4a8aa330fd2b5a50a25a": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r3-a/file-ops-r3-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19107,
        "output_tokens": 30,
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
    "planner": 16,
    "locator": 0,
    "total": 16,
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
      "task": "file-ops",
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
      "task": "file-ops",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
