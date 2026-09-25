# computer_use benchmark

- Run label: `multi-select-copy-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| multi-select-copy | 0/1 | 0% | 0%–79% | 15 | 13 | 16 | 15 | 40 | 131526 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| multi-select-copy | 16 | 1.6 | 2.2 | 40 | 0.0 |

- API calls total: 16, mean 2.5s/call, median streamed ttft 1.6, LLM time total 40s

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
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260925-m6-tasks-runtime"
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
      "charged_tokens": 131526,
      "charged_nano_usd": 0,
      "known_tokens": 131526,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 131526,
        "charged_nano_usd": 0,
        "known_tokens": 131526,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "df540dd59ad840908283c0b0abdfc0ce": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5138,
        "output_tokens": 50,
        "status": "known"
      },
      "183e78e6b24b4e56baeebc76f16f4e2c": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5218,
        "output_tokens": 13,
        "status": "known"
      },
      "06d0b598b28b4b6eb523482d240cb6f3": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4838,
        "output_tokens": 27,
        "status": "known"
      },
      "363c3733620840c187c091dfa233f741": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4895,
        "output_tokens": 13,
        "status": "known"
      },
      "23ec67928f0b4562bba48660a20589a9": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7062,
        "output_tokens": 63,
        "status": "known"
      },
      "44f793a4f9b040f4be7c38d3794323e7": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7146,
        "output_tokens": 46,
        "status": "known"
      },
      "628c8a0de2844ab9814bdb8f757a36d2": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7231,
        "output_tokens": 38,
        "status": "known"
      },
      "16af9d9709584ae88983e8278207f7c4": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7289,
        "output_tokens": 23,
        "status": "known"
      },
      "89fef8096b094899ae8fdb6aa43b7642": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9464,
        "output_tokens": 81,
        "status": "known"
      },
      "4f0f53cc4b174f21b80db47779c67a8d": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8853,
        "output_tokens": 69,
        "status": "known"
      },
      "1c2a9baeaff74ae8ba0a39afdd4217a6": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8969,
        "output_tokens": 48,
        "status": "known"
      },
      "0777297026e74e38ae4439be2d89cfef": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9039,
        "output_tokens": 36,
        "status": "known"
      },
      "9550a551197741868677f5939cec3916": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11227,
        "output_tokens": 119,
        "status": "known"
      },
      "7bdeb5e7ef0140fa847e4fc01201b9ac": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11394,
        "output_tokens": 49,
        "status": "known"
      },
      "1a532999055f463d88c55651e31a1d36": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11482,
        "output_tokens": 37,
        "status": "known"
      },
      "1229be0b10694a87a5d730a413dcbebb": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-a/multi-select-copy-r2-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11539,
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
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "multi-select-copy",
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
      "task": "multi-select-copy",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
